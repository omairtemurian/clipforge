"""The LLM Director (SPEC-v3 3.5, 1.6): a Pro Edit plan written by the
configured LLM, falling back to the rule-based Director.

1. The rule-based plan of the same request is made first (director_rules):
   it is the fallback and sizes the cost estimate (director_cost).
2. Without an LLM the rule plan is the answer. Otherwise the messages are
   built (director_prompt) and, before every call, the monthly cap is
   checked against one call of the estimate.
3. The reply must be a DirectorReply (Pydantic) whose items make a valid
   plan: kinds the preset allows, typed params, times within the clip, no
   overlaps per track (edl.plan_problems) and assets of the catalog
   (director_catalog). An invalid reply is sent back with its problems up
   to MAX_RETRIES times.
4. A valid plan is post-processed like the rule-based one (the loop
   ending when the request asks for it, its composite moves placed whole
   by the rule-based Director's code (director_expand), snapping,
   punchline protection,
   reaction holds, budgets, pattern interrupts in the gaps, whooshes) and
   checked again.
5. When the LLM cannot be reached, never sends a valid plan, the cap is
   reached or post-processing leaves a problem, the result is the rule
   plan with the reason (fallback).

Every call made with an engine records its tokens in the usage meter as
PROEDIT at the owner's price, inside the caller's job if there is one.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import Engine

from clipforge import config
from clipforge.llm import LLMClient, LLMError, reply_json
from clipforge.models import ProEditPlan
from clipforge.pipeline.curate_prompt import describe_errors
from clipforge.proedit.audio.sfx_place import place_whooshes
from clipforge.proedit.budgets import budget_problems, effective_budget
from clipforge.proedit.config import ProEditConfig
from clipforge.proedit.director_catalog import catalog_problems
from clipforge.proedit.director_cost import (
    MAX_CALLS,
    CostEstimate,
    ProEditCapExceeded,
    check_monthly_cap,
    estimate_cost,
    metered,
    usd_per_token,
)
from clipforge.proedit.director_expand import (
    expand_composites,
    moment_anchors,
    moment_problems,
)
from clipforge.proedit.director_prompt import (
    DirectorReply,
    DirectorRequest,
    reply_text,
    system_prompt,
    user_prompt,
)
from clipforge.proedit.director_result import DirectorResult, composite_left_outs
from clipforge.proedit.director_rules import RulePlan, rule_plan
from clipforge.proedit.edl import plan_problems
from clipforge.proedit.pacing import reaction_holds
from clipforge.proedit.postprocess import postprocess_plan
from clipforge.proedit.retention import add_loop_ending, fill_plan
from clipforge.proedit.signals import plan_timing
from clipforge.proedit.snap import PlanNote

logger = logging.getLogger(__name__)

CREATED_BY = "director"
NO_LLM = "no LLM is configured"


@dataclass
class _Run:
    calls: int = 0
    invalid: list[list[str]] = field(default_factory=list)
    tally: list[int] = field(default_factory=list)


def reply_plan(
    reply: str, request: DirectorRequest
) -> tuple[ProEditPlan | None, list[str]]:
    """Return the plan of a Director reply for request, or None and the
    problems that make it invalid (step 3)."""
    try:
        parsed = DirectorReply.model_validate_json(reply_json(reply))
        plan = ProEditPlan.model_validate(
            {
                "id": request.plan_id,
                "clip_id": request.signals.clip_id,
                "preset": request.preset_id,
                "intensity": request.intensity,
                "style_recipe_id": request.recipe.id if request.recipe else None,
                "version": request.version,
                "rationale": parsed.rationale,
                "created_by": CREATED_BY,
                "items": [
                    {"id": n, **item, "source": "auto"}
                    for n, item in enumerate(
                        [
                            *(i.model_dump() for i in parsed.items),
                            *moment_anchors(parsed.moments, request),
                        ],
                        start=1,
                    )
                ],
            }
        )
    except ValidationError as error:
        return None, [
            line.removeprefix("- ") for line in describe_errors(error).splitlines()
        ]
    problems = [
        f"item {item.id} ({item.kind}): the {request.preset.name} preset does "
        f"not use {item.kind}"
        for item in plan.items
        if item.kind not in request.preset.kinds
    ]
    problems += moment_problems(parsed.moments, request)
    problems += plan_problems(plan, request.signals.duration)
    problems += catalog_problems(plan.items, request.catalog)
    return (None, problems) if problems else (plan, [])


def finish_plan(
    plan: ProEditPlan, request: DirectorRequest, interrupts: bool = True
) -> tuple[ProEditPlan, list[PlanNote], list[str]]:
    """Post-process a valid plan like the rule-based one (step 4); return it,
    the notes and what is still wrong with it (empty: nothing). Without
    interrupts the interrupt gaps stay open (a critic revision that
    removed moves keeps them removed)."""
    preset, signals = request.preset, request.signals
    beats = request.music.beats(signals.duration) if request.music else ()
    timing = plan_timing(signals, beats)
    preset_budget = preset.budgets.get(request.intensity)
    budget = effective_budget(request.intensity, preset_budget)
    loop_notes: list[PlanNote] = []
    if request.loop_ending:
        items, loop_notes = add_loop_ending(plan.items, timing)
        plan = plan.model_copy(update={"items": items})
    plan, expand_notes = expand_composites(plan, timing, budget, preset)
    loop_notes += expand_notes
    done = postprocess_plan(plan, timing, preset_budget, preset.snap)
    holds = reaction_holds(timing, request.intensity)
    filled = done.plan
    if interrupts:
        filled, _ = fill_plan(done.plan, timing, budget, preset, holds)
    placed = place_whooshes(
        filled, timing, signals.scene_cuts, preset_budget, preset.whooshes
    )
    problems = plan_problems(placed.plan, signals.duration)
    problems += budget_problems(placed.plan.items, budget, signals.duration)
    return placed.plan, [*loop_notes, *done.notes, *placed.notes], problems


def _ask(
    llm: LLMClient,
    request: DirectorRequest,
    estimate: CostEstimate,
    run: _Run,
    engine: Engine | None,
    cfg: ProEditConfig,
    now: datetime | None,
) -> ProEditPlan | None:
    """Ask llm until a reply is valid (steps 2-3); None after MAX_CALLS."""
    system = system_prompt(request.preset)
    problems: list[str] = []
    for attempt in range(1, MAX_CALLS + 1):
        if engine is not None:
            check_monthly_cap(engine, cfg, estimate, now)
        run.calls += 1
        reply = llm.complete_json(system, user_prompt(request, problems))
        plan, problems = reply_plan(reply, request)
        if plan is not None:
            return plan
        run.invalid.append(problems)
        logger.warning(
            "clip %d: Director reply %d of %d is not valid:\n%s",
            request.signals.clip_id,
            attempt,
            MAX_CALLS,
            "\n".join(problems),
        )
    return None


def director_plan(
    request: DirectorRequest,
    llm: LLMClient | None,
    *,
    engine: Engine | None = None,
    project_id: int | None = None,
    cfg: ProEditConfig | None = None,
    now: datetime | None = None,
) -> DirectorResult:
    """Return the plan of request (module docstring): the LLM's when llm
    sends a valid one, else the rule-based Director's with the reason. With
    engine, every call is metered for project_id and capped (cfg: default
    the app's proedit settings; now: the month of the cap)."""
    cfg = config.settings.proedit if cfg is None else cfg
    rules = rule_plan(
        request.signals,
        request.preset,
        request.preset_id,
        request.intensity,
        request.music,
        plan_id=request.plan_id,
        version=request.version,
        style_recipe_id=request.recipe.id if request.recipe else None,
        loop_ending=request.loop_ending,
    )
    if llm is None:
        return _fallback(rules, NO_LLM)
    estimate = estimate_cost(
        system_prompt(request.preset),
        user_prompt(request),
        reply_text(rules.plan),
        cfg,
    )
    run = _Run()
    try:
        with metered(engine, project_id, cfg, run.tally):
            plan = _ask(llm, request, estimate, run, engine, cfg, now)
    except ProEditCapExceeded as error:
        return _fallback(rules, str(error), estimate, run, cfg)
    except LLMError as error:
        reason = f"the LLM request failed: {error}"
        return _fallback(rules, reason, estimate, run, cfg)
    if plan is None:
        reason = f"the LLM sent no valid plan in {MAX_CALLS} tries"
        return _fallback(rules, reason, estimate, run, cfg)
    final, notes, problems = finish_plan(plan, request)
    if problems:
        reason = "the LLM's plan breaks rules after post-processing: " + "; ".join(
            problems
        )
        return _fallback(rules, reason, estimate, run, cfg)
    return DirectorResult(
        plan=final,
        notes=notes,
        estimate=estimate,
        calls=run.calls,
        invalid_replies=run.invalid,
        tokens=sum(run.tally),
        cost_usd=_cost(run, cfg),
    )


def _cost(run: _Run, cfg: ProEditConfig) -> float | None:
    price = usd_per_token(cfg)
    return None if price is None else sum(run.tally) * price


def _fallback(
    rules: RulePlan,
    reason: str,
    estimate: CostEstimate | None = None,
    run: _Run | None = None,
    cfg: ProEditConfig | None = None,
) -> DirectorResult:
    """The rule-based plan as the result, with why (step 5)."""
    logger.info("clip %d: rule-based plan (%s)", rules.plan.clip_id, reason)
    run = run or _Run()
    return DirectorResult(
        plan=rules.plan,
        notes=rules.notes,
        estimate=estimate,
        calls=run.calls,
        invalid_replies=run.invalid,
        tokens=sum(run.tally),
        cost_usd=None if cfg is None or not run.calls else _cost(run, cfg),
        fallback=reason,
        left_out=composite_left_outs(rules.left_out),
    )
