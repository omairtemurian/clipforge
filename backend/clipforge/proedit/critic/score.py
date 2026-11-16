"""The Pro Edit critic's scores (SPEC-v3 3.7, 1.6).

1. The model must see images (capability.check_vision, probed once per
   model). Without vision Pro Edit runs the Director only: the result is
   director_only with the message the UI shows, and no critic call is made.
2. The request (prompt.CriticRequest) holds the sampled frames of the proxy
   render (sample) and its audio summary (audio_summary); critic_request
   makes them from a render.
3. The estimate counts the text tokens like the Director's (director_cost)
   plus each image's visual tokens, ceil(w / 28) x ceil(h / 28) (the 28-px
   patch rule of Anthropic's vision guide; other providers bill about as
   much or less for a 360-px frame), and a reply as long as
   prompt.example_reply. Before every call the monthly cap is checked
   against one call of the estimate.
4. The reply must be a CriticReply (every check exactly once, scores 0 to
   10, well-formed changes); an invalid one is sent back with its problems
   up to MAX_RETRIES times. The scores come back in the checklist's order
   with the reply's EDL changes (revise applies them).
5. When the LLM fails, never sends a valid reply or the cap is reached
   (cap_reached), the result has no scores and says why (failure); the
   edit stays as it is.

Every call made with an engine (the vision probe included) records its
tokens in the usage meter as PROEDIT at the owner's price.
"""

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import Engine

from clipforge import config
from clipforge.llm import LLMClient, LLMError, reply_json
from clipforge.models import CriticScore, ProEditPlan
from clipforge.pipeline.curate_prompt import describe_errors
from clipforge.proedit.config import ProEditConfig
from clipforge.proedit.critic.audio_summary import summarize_audio
from clipforge.proedit.critic.capability import VisionCheck, check_vision
from clipforge.proedit.critic.changes import CriticChange
from clipforge.proedit.critic.prompt import (
    CHECKS,
    CriticReply,
    CriticRequest,
    example_reply,
    system_prompt,
    user_prompt,
)
from clipforge.proedit.critic.sample import (
    SampledFrame,
    extract_frames,
    sample_frames,
)
from clipforge.proedit.critic.vision import complete_with_images
from clipforge.proedit.director_catalog import CatalogAsset
from clipforge.proedit.director_cost import (
    MAX_CALLS,
    CostEstimate,
    ProEditCapExceeded,
    check_monthly_cap,
    metered,
    tokens_of,
    usd_per_token,
)
from clipforge.proedit.preset_defs import PresetDef
from clipforge.proedit.signal_models import ProEditSignals

logger = logging.getLogger(__name__)

PATCH_PX = 28
WHO = "the critic"


@dataclass(frozen=True)
class CriticResult:
    """What the critic said: the scores in the checklist's order (empty
    when it did not score) and the EDL changes it asks for, whether Pro
    Edit runs the Director only and the message why, the estimate shown
    before the calls, the LLM calls made, the problems of each invalid
    reply, the tokens the answers reported and their cost (None: no price
    set), and why the critic gave no scores (failure; None when it did or
    when it is director-only; cap_reached: the monthly cap stopped it)."""

    scores: list[CriticScore]
    changes: list[CriticChange] = field(default_factory=list)
    director_only: bool = False
    message: str | None = None
    estimate: CostEstimate | None = None
    calls: int = 0
    invalid_replies: list[list[str]] = field(default_factory=list)
    tokens: int = 0
    cost_usd: float | None = None
    failure: str | None = None
    cap_reached: bool = False


@dataclass
class _Run:
    calls: int = 0
    invalid: list[list[str]] = field(default_factory=list)
    tally: list[int] = field(default_factory=list)


def image_tokens(frame: SampledFrame) -> int:
    """Return the estimated visual tokens of a frame image (step 3)."""
    return math.ceil(frame.width / PATCH_PX) * math.ceil(frame.height / PATCH_PX)


def estimate_critic_cost(request: CriticRequest, cfg: ProEditConfig) -> CostEstimate:
    """Return the estimate of one critic call for request (step 3)."""
    input_tokens = tokens_of(system_prompt()) + tokens_of(user_prompt(request))
    input_tokens += sum(image_tokens(frame) for frame in request.frames)
    output_tokens = tokens_of(example_reply())
    price = usd_per_token(cfg)
    return CostEstimate(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        max_calls=MAX_CALLS,
        usd=None if price is None else (input_tokens + output_tokens) * price,
    )


def parse_reply(reply: str) -> tuple[CriticReply | None, list[str]]:
    """Return a critic reply, or None and the problems that make it invalid
    (step 4)."""
    try:
        return CriticReply.model_validate_json(reply_json(reply)), []
    except ValidationError as error:
        return None, [
            line.removeprefix("- ") for line in describe_errors(error).splitlines()
        ]


def ranked_scores(parsed: CriticReply) -> list[CriticScore]:
    """Return the scores of a valid reply in the checklist's order."""
    order = list(CHECKS)
    ranked = sorted(parsed.scores, key=lambda s: order.index(s.check))
    return [CriticScore(**s.model_dump()) for s in ranked]


def reply_scores(reply: str) -> tuple[list[CriticScore] | None, list[str]]:
    """Return the scores of a critic reply in the checklist's order, or
    None and the problems that make it invalid (step 4)."""
    parsed, problems = parse_reply(reply)
    return (None, problems) if parsed is None else (ranked_scores(parsed), [])


def below_threshold(scores: list[CriticScore], threshold: float) -> list[CriticScore]:
    """Return the scores under threshold (what a revision must fix)."""
    return [s for s in scores if s.score < threshold]


def passes(scores: list[CriticScore], threshold: float) -> bool:
    """Whether every check scored at least threshold (an empty list does
    not pass: nothing was judged)."""
    return bool(scores) and not below_threshold(scores, threshold)


def critic_request(
    video: Path,
    plan: ProEditPlan,
    preset: PresetDef,
    signals: ProEditSignals,
    cfg: ProEditConfig | None = None,
    catalog: Sequence[CatalogAsset] = (),
) -> CriticRequest:
    """Return the critic's request for the proxy render video of plan:
    at most proedit.critic_max_frames frames, the audio summary, the
    passing score (proedit.critic_threshold) and the assets of catalog a
    change may name. Raises StepError if ffmpeg cannot read the render."""
    cfg = config.settings.proedit if cfg is None else cfg
    samples = sample_frames(
        plan.items, signals.duration, signals.fps, cfg.critic_max_frames
    )
    return CriticRequest(
        plan=plan,
        preset=preset,
        signals=signals,
        frames=extract_frames(video, samples),
        audio=summarize_audio(video, plan.items, signals.words, signals.duration),
        threshold=cfg.critic_threshold,
        catalog=catalog,
    )


def _ask(
    llm: LLMClient,
    request: CriticRequest,
    estimate: CostEstimate,
    run: _Run,
    engine: Engine | None,
    cfg: ProEditConfig,
    now: datetime | None,
) -> CriticReply | None:
    """Ask llm until a reply is valid (step 4); None after MAX_CALLS."""
    system = system_prompt()
    images = [frame.image for frame in request.frames]
    problems: list[str] = []
    for attempt in range(1, MAX_CALLS + 1):
        if engine is not None:
            check_monthly_cap(engine, cfg, estimate, now, who=WHO)
        run.calls += 1
        reply = complete_with_images(
            llm, system, user_prompt(request, problems), images
        )
        parsed, problems = parse_reply(reply)
        if parsed is not None:
            return parsed
        run.invalid.append(problems)
        logger.warning(
            "clip %d: critic reply %d of %d is not valid:\n%s",
            request.signals.clip_id,
            attempt,
            MAX_CALLS,
            "\n".join(problems),
        )
    return None


def critique(
    request: CriticRequest,
    llm: LLMClient | None,
    *,
    engine: Engine | None = None,
    project_id: int | None = None,
    cfg: ProEditConfig | None = None,
    now: datetime | None = None,
) -> CriticResult:
    """Return the critic's scores of request (module docstring). With
    engine, every call is metered for project_id and capped (cfg: default
    the app's proedit settings; now: the month of the cap)."""
    cfg = config.settings.proedit if cfg is None else cfg
    run = _Run()
    with metered(engine, project_id, cfg, run.tally):
        vision: VisionCheck = check_vision(llm)
    if llm is None or vision.director_only:
        return CriticResult(
            scores=[],
            director_only=True,
            message=vision.message,
            tokens=sum(run.tally),
            cost_usd=_cost(run, cfg),
        )
    estimate = estimate_critic_cost(request, cfg)
    failure: str | None = None
    capped = False
    parsed: CriticReply | None = None
    try:
        with metered(engine, project_id, cfg, run.tally):
            parsed = _ask(llm, request, estimate, run, engine, cfg, now)
    except ProEditCapExceeded as error:
        failure, capped = str(error), True
    except LLMError as error:
        failure = f"the LLM request failed: {error}"
    if parsed is None and failure is None:
        failure = f"the LLM sent no valid scores in {MAX_CALLS} tries"
    if failure is not None:
        logger.info("clip %d: no critic scores (%s)", request.signals.clip_id, failure)
    return CriticResult(
        scores=[] if parsed is None else ranked_scores(parsed),
        changes=[] if parsed is None else list(parsed.changes),
        estimate=estimate,
        calls=run.calls,
        invalid_replies=run.invalid,
        tokens=sum(run.tally),
        cost_usd=_cost(run, cfg),
        failure=failure,
        cap_reached=capped,
    )


def _cost(run: _Run, cfg: ProEditConfig) -> float | None:
    price = usd_per_token(cfg)
    return None if price is None or not run.tally else sum(run.tally) * price
