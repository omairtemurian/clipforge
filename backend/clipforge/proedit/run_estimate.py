"""The cost estimate a Pro Edit dialog shows before a run (SPEC-v3 1.6,
3.8): the LLM tokens and USD of the Director and of the critic at most.

The Director's estimate is the one director_plan checks the cap with (its
prompts for the clip's real signals and the rule-based plan's length as the
reply). The critic's is one call per round for the frames it would see of
that plan (critic.sample.sample_frames at the proxy's width) with every
retry, times proedit.critic_max_rounds; its images are sized but not
rendered and its audio summary is a silent curve of the clip's length,
which are what the call's tokens depend on. Nothing calls the LLM.
"""

import math
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import config
from clipforge.aspect import aspect_size
from clipforge.db import ProjectRow
from clipforge.models import Clip, ProEditEstimate, ProEditOptions, ProEditPlan
from clipforge.proedit.config import ProEditConfig
from clipforge.proedit.critic.audio_summary import CURVE_STEP_S, AudioSummary
from clipforge.proedit.critic.prompt import CriticRequest
from clipforge.proedit.critic.sample import FRAME_WIDTH, SampledFrame, sample_frames
from clipforge.proedit.critic.score import estimate_critic_cost
from clipforge.proedit.critic.vision import Image
from clipforge.proedit.director_cost import (
    CostEstimate,
    estimate_cost,
    month_spend_usd,
    usd_text,
)
from clipforge.proedit.director_prompt import (
    DirectorRequest,
    reply_text,
    system_prompt,
    user_prompt,
)
from clipforge.proedit.director_rules import rule_plan
from clipforge.proedit.run_inputs import director_request


def run_estimate(
    engine: Engine,
    clip: Clip,
    options: ProEditOptions,
    work: Path,
    cfg: ProEditConfig | None = None,
    now: datetime | None = None,
) -> ProEditEstimate:
    """Return the estimate of a Pro Edit of clip with options (module
    docstring); work is the work directory of its project's process job.
    Raises RunInputError for a missing recipe or music and StepError for
    missing signals."""
    cfg = config.settings.proedit if cfg is None else cfg
    request = director_request(engine, clip, options, work)
    plan = rule_plan(
        request.signals,
        request.preset,
        request.preset_id,
        request.intensity,
        request.music,
        style_recipe_id=options.style_recipe_id,
        loop_ending=request.loop_ending,
    ).plan
    director = estimate_cost(
        system_prompt(request.preset), user_prompt(request), reply_text(plan), cfg
    )
    rounds = cfg.critic_max_rounds if options.use_critic else 0
    with Session(engine) as session:
        aspect = session.get_one(ProjectRow, clip.project_id).settings.aspect
    critic = critic_estimate(plan, request, aspect, cfg)
    critic_usd = None if critic.max_usd is None else critic.max_usd * rounds
    spent = month_spend_usd(engine, now)
    cap = cfg.monthly_cap_usd
    return ProEditEstimate(
        director_tokens=director.tokens * director.max_calls,
        director_usd=director.max_usd,
        critic_tokens=critic.tokens * critic.max_calls * rounds,
        critic_usd=critic_usd,
        critic_rounds=rounds,
        text=_text(director, critic, rounds),
        monthly_cap_usd=cap,
        month_spend_usd=spent,
        blocked=cap is not None
        and director.usd is not None
        and spent + director.usd > cap,
    )


def critic_estimate(
    plan: ProEditPlan, request: DirectorRequest, aspect: str, cfg: ProEditConfig
) -> CostEstimate:
    """Return the estimate of one critic call on plan's proxy in aspect for
    the clip of request (module docstring)."""
    signals = request.signals
    width, height = aspect_size(aspect)
    frame_height = 2 * round(FRAME_WIDTH * height / width / 2)
    frames = [
        SampledFrame(sample, Image(b"", "image/jpeg"), FRAME_WIDTH, frame_height)
        for sample in sample_frames(
            plan.items, signals.duration, signals.fps, cfg.critic_max_frames
        )
    ]
    silent = [0.0] * max(1, math.ceil(signals.duration / CURVE_STEP_S))
    audio = AudioSummary(
        integrated_lufs=None,
        true_peak_dbtp=None,
        peak_dbfs=0.0,
        clipped_samples=0,
        loudness_curve=silent,
        speech_db=None,
        music_db=None,
        sfx_db=None,
        speech_over_music_db=None,
    )
    judged = CriticRequest(
        plan=plan,
        preset=request.preset,
        signals=signals,
        frames=frames,
        audio=audio,
        threshold=cfg.critic_threshold,
        catalog=request.catalog,
    )
    return estimate_critic_cost(judged, cfg)


def _text(director: CostEstimate, critic: CostEstimate, rounds: int) -> str:
    """The estimate as the dialog shows it."""
    if rounds == 0:
        return f"{director.text()} No critic rounds."
    most = critic.tokens * critic.max_calls * rounds
    cost = "" if critic.max_usd is None else f" ({usd_text(critic.max_usd * rounds)})"
    return (
        f"{director.text()} The critic adds at most {most:,} tokens{cost} "
        f"over {rounds} round(s)."
    )
