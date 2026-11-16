"""The Pro Edit critic loop (SPEC-v3 3.7): rounds of scores and revisions
of a plan, at most proedit.critic_max_rounds (0 to 3; 0: no critic).

Without vision (capability.check_vision, probed once per model and
metered) or without an LLM the loop stops at once (director_only) with the
message the UI shows, before anything is rendered. Each round n of N:
1. From the second round on, the monthly cap is checked against one call
   of the last round's estimate before anything is rendered: reached, the
   loop stops (cap) and the plan stays as it is.
2. on_round(n, N) reports progress; the plan's proxy is rendered (render)
   and the critic scores it (score.critique).
3. No scores (the cap, a failing LLM, no valid reply): the loop stops
   (cap or failed) and the plan stays as it is.
4. Every score reaches proedit.critic_threshold: the loop stops early
   (passed).
5. Otherwise the critic's changes revise the plan (apply.revise_plan); the
   revision is stored (store, which gives it its id) and the next round
   judges it. No revision (every change ignored or undone): the loop stops
   (no_changes).
After round N the loop stops (max_rounds) with the last revision, whose
changes code validated but no round judged.

Each round is a CriticRound: the scores of the plan version it judged and
"what changed" (the diff, the ignored changes and why, notes).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine

from clipforge import config
from clipforge.llm import LLMClient
from clipforge.models import CriticRound, ProEditPlan
from clipforge.proedit.config import ProEditConfig
from clipforge.proedit.critic.apply import revise_plan
from clipforge.proedit.critic.capability import check_vision
from clipforge.proedit.critic.score import (
    CriticResult,
    critic_request,
    critique,
    passes,
)
from clipforge.proedit.director_cost import (
    CostEstimate,
    ProEditCapExceeded,
    check_monthly_cap,
    metered,
    usd_per_token,
)
from clipforge.proedit.director_prompt import DirectorRequest

logger = logging.getLogger(__name__)

StopReason = Literal[
    "off", "passed", "max_rounds", "no_changes", "director_only", "cap", "failed"
]
WHO = "the critic's next round"


@dataclass(frozen=True)
class CriticLoopResult:
    """The plan after the loop (the last revision, or the plan it started
    from), the revisions in order, the rounds, why the loop stopped and the
    message for the UI (director-only, cap or failure), the estimate of one
    critic call, and the LLM calls, tokens and cost (None: no price set or
    no call) of every round."""

    plan: ProEditPlan
    revisions: list[ProEditPlan] = field(default_factory=list)
    rounds: list[CriticRound] = field(default_factory=list)
    stopped: StopReason = "off"
    message: str | None = None
    estimate: CostEstimate | None = None
    calls: int = 0
    tokens: int = 0
    cost_usd: float | None = None


@dataclass
class _Totals:
    calls: int = 0
    tokens: int = 0
    cost_usd: float | None = None
    estimate: CostEstimate | None = None

    def add(self, result: CriticResult) -> None:
        self.calls += result.calls
        self.tokens += result.tokens
        if result.cost_usd is not None:
            self.cost_usd = (self.cost_usd or 0.0) + result.cost_usd
        if result.estimate is not None:
            self.estimate = result.estimate


def _keep(plan: ProEditPlan) -> ProEditPlan:
    return plan


def _cap_message(
    engine: Engine | None,
    cfg: ProEditConfig,
    estimate: CostEstimate | None,
    now: datetime | None,
) -> str | None:
    """Return why the cap blocks another round (step 1), None if it does
    not."""
    if engine is None or estimate is None:
        return None
    try:
        check_monthly_cap(engine, cfg, estimate, now, who=WHO)
    except ProEditCapExceeded as error:
        return str(error)
    return None


def critic_loop(
    plan: ProEditPlan,
    request: DirectorRequest,
    render: Callable[[ProEditPlan], Path],
    llm: LLMClient | None,
    *,
    engine: Engine | None = None,
    project_id: int | None = None,
    cfg: ProEditConfig | None = None,
    now: datetime | None = None,
    store: Callable[[ProEditPlan], ProEditPlan] = _keep,
    on_round: Callable[[int, int], None] | None = None,
) -> CriticLoopResult:
    """Run the critic's rounds on plan (module docstring) for the clip,
    preset, intensity, music and catalog of request: render returns the
    proxy render of a plan; store saves a revision and returns it with its
    id (default: kept as is). With engine, every call is metered for
    project_id and capped (cfg: default the app's proedit settings; now:
    the month of the cap)."""
    cfg = config.settings.proedit if cfg is None else cfg
    total_rounds = cfg.critic_max_rounds
    current = plan
    revisions: list[ProEditPlan] = []
    rounds: list[CriticRound] = []
    totals = _Totals()

    def done(stopped: StopReason, message: str | None = None) -> CriticLoopResult:
        logger.info(
            "clip %d: critic stopped after %d round(s): %s",
            plan.clip_id,
            len(rounds),
            stopped,
        )
        return CriticLoopResult(
            plan=current,
            revisions=revisions,
            rounds=rounds,
            stopped=stopped,
            message=message,
            estimate=totals.estimate,
            calls=totals.calls,
            tokens=totals.tokens,
            cost_usd=totals.cost_usd,
        )

    if total_rounds == 0:
        return done("off")
    tally: list[int] = []
    with metered(engine, project_id, cfg, tally):
        vision = check_vision(llm)
    totals.tokens += sum(tally)
    price = usd_per_token(cfg)
    if price is not None and tally:
        totals.cost_usd = sum(tally) * price
    if llm is None or vision.director_only:
        return done("director_only", vision.message)
    for n in range(1, total_rounds + 1):
        if n > 1 and (blocked := _cap_message(engine, cfg, totals.estimate, now)):
            return done("cap", blocked)
        if on_round is not None:
            on_round(n, total_rounds)
        judged = critic_request(
            render(current),
            current,
            request.preset,
            request.signals,
            cfg,
            request.catalog,
        )
        result = critique(
            judged, llm, engine=engine, project_id=project_id, cfg=cfg, now=now
        )
        totals.add(result)
        if result.director_only:
            return done("director_only", result.message)
        if result.failure is not None:
            return done("cap" if result.cap_reached else "failed", result.failure)
        scores = CriticRound(
            round=n, scores=result.scores, plan_version=current.version
        )
        if passes(result.scores, cfg.critic_threshold):
            rounds.append(scores)
            return done("passed")
        revision = revise_plan(current, result.changes, request)
        rounds.append(
            scores.model_copy(
                update={
                    "changes": revision.changes,
                    "ignored": revision.ignored,
                    "notes": revision.notes,
                }
            )
        )
        if revision.plan is None:
            return done("no_changes")
        current = store(revision.plan)
        revisions.append(current)
    return done("max_rounds")
