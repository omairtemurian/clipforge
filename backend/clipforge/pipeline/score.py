"""Score step (SPEC 6.6): rank the clip candidates by virality -> scored.json.

Each candidate of candidates.json (curate) gets three components from 0 to
1, from its LLM scores and the events of signals.json (signals):
- llm: the mean of its hook, flow, value and trend scores, over 99;
- laugh: the highest intensity of the laugh events in the window from 3 s
  before its end to 2 s after it, 0 if there is none: the laugh that the
  punchline at the end of a clip gets;
- energy: the fraction of the clip that energy-peak, applause and cheer
  events cover.
Its overall score is round(99 * the weighted sum of the components), with
the weights of cfg.score_weights scaled to sum to 1. Laughs only count for
comedy: for the other genres the laugh weighs 0 and the other two weights
are scaled up to sum to 1 again. The candidates are sorted by overall score,
best first, and the first processing.num_clips are written to scored.json.
"""

import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Literal, get_args

from clipforge.models import (
    CandidateList,
    ClipCandidate,
    ContentGenre,
    ScoredCandidate,
    ScoredList,
    Scores,
    SignalEvent,
    SignalList,
)
from clipforge.pipeline.curate_select import llm_average
from clipforge.pipeline.genre import job_genre
from clipforge.pipeline.signal_merge import CROWD_KINDS
from clipforge.pipeline.step import (
    CANDIDATES,
    SCORED,
    SIGNALS,
    StepError,
    StepSettings,
    is_done,
    load_json,
    load_meta,
    write_json,
)

logger = logging.getLogger(__name__)

# The parts of the overall score: the names of the cfg.score_weights.
Component = Literal["llm", "laugh", "energy"]
COMPONENTS: tuple[Component, ...] = get_args(Component)
# Laughs count from this long before a clip's end to this long after it.
LAUGH_BEFORE_END_S = 3.0
LAUGH_AFTER_END_S = 2.0
# The highest LLM score and overall score.
MAX_SCORE = 99
# Times are compared, and energy scores rounded, to milliseconds / 3 decimals.
DECIMALS = 3


def component_weights(
    genre: ContentGenre, configured: Mapping[str, float]
) -> dict[Component, float]:
    """Return the weight of each score component for the clips of genre.

    The weights are those of configured (cfg.score_weights), where a
    component it does not name weighs 0; unless genre is comedy, laugh
    weighs 0. They are scaled to sum to 1. Raises StepError if configured
    names another component or has a weight that is negative or not finite,
    or if it gives no weight to the components that count for genre.
    """
    unknown = sorted(set(configured) - set(COMPONENTS))
    if unknown:
        raise StepError(
            f"score_weights has unknown components: {', '.join(unknown)}; "
            f"use {', '.join(COMPONENTS)}"
        )
    bad = [f"{name} {w}" for name, w in configured.items() if not 0 <= w < math.inf]
    if bad:
        raise StepError(f"score_weights must be numbers >= 0, not {', '.join(bad)}")
    counted = [name for name in COMPONENTS if genre == "comedy" or name != "laugh"]
    raw = {name: configured.get(name, 0.0) for name in counted}
    total = math.fsum(raw.values())
    if total == 0:
        raise StepError(
            f"score_weights give no weight to {', '.join(counted)}, "
            f"the components of {genre} clips"
        )
    return {name: raw.get(name, 0.0) / total for name in COMPONENTS}


def in_window(event: SignalEvent, start: float, end: float) -> bool:
    """Return True if event overlaps the window from start to end seconds.

    Both are closed: an event that ends at start or starts at end is in the
    window. Times are compared to the millisecond, so float noise, as in
    32.2 - 3 = 29.200000000000003, cannot move an event out.
    """
    return (
        round(event.end - start, DECIMALS) >= 0
        and round(end - event.start, DECIMALS) >= 0
    )


def laugh_score(end: float, events: Iterable[SignalEvent]) -> float:
    """Return the laugh component of a clip that ends at end seconds.

    It is the highest intensity of the laugh events in the window
    [end - LAUGH_BEFORE_END_S, end + LAUGH_AFTER_END_S] (in_window), or 0
    if there is none. Other kinds of events, applause too, do not count.
    """
    low, high = end - LAUGH_BEFORE_END_S, end + LAUGH_AFTER_END_S
    return max(
        (e.intensity for e in events if e.kind == "laugh" and in_window(e, low, high)),
        default=0.0,
    )


def energy_score(start: float, end: float, events: Iterable[SignalEvent]) -> float:
    """Return the energy component of the clip from start to end seconds.

    It is the fraction of the clip that energy-peak, applause and cheer
    events (CROWD_KINDS) cover, rounded to DECIMALS and capped at 1; time that
    several events cover counts once. Music does not count.
    A clip that does not end after its start has 0.
    """
    if end <= start:
        return 0.0
    spans = sorted(
        (max(e.start, start), min(e.end, end))
        for e in events
        if (e.kind == "energy_peak" or e.kind in CROWD_KINDS)
        and e.start < end
        and e.end > start
    )
    covered, reach = 0.0, start
    for span_start, span_end in spans:
        if span_end > reach:
            covered += span_end - max(span_start, reach)
            reach = span_end
    return min(round(covered / (end - start), DECIMALS), 1.0)


def score_candidate(
    candidate: ClipCandidate,
    events: Sequence[SignalEvent],
    weights: Mapping[Component, float],
) -> ScoredCandidate:
    """Return candidate with its scores (SPEC 6.6).

    The components are llm (llm_average over MAX_SCORE), laugh_score and
    energy_score, and overall is round(MAX_SCORE * their sum weighted by
    weights). The scores keep the LLM's hook, flow, value and trend, and the
    laugh and energy components, also when one of them weighs 0.
    """
    laugh = laugh_score(candidate.end, events)
    energy = energy_score(candidate.start, candidate.end, events)
    parts: dict[Component, float] = {
        "llm": llm_average(candidate) / MAX_SCORE,
        "laugh": laugh,
        "energy": energy,
    }
    weighted = math.fsum(weights[name] * parts[name] for name in COMPONENTS)
    scores = Scores(
        overall=round(MAX_SCORE * weighted),
        hook=candidate.hook,
        flow=candidate.flow,
        value=candidate.value,
        trend=candidate.trend,
        laugh=laugh,
        energy=energy,
    )
    return ScoredCandidate(**candidate.model_dump(), scores=scores)


def rank(scored: Iterable[ScoredCandidate], count: int) -> list[ScoredCandidate]:
    """Return the count candidates with the highest overall score, best first.

    Candidates with equal overall scores keep their order.
    """
    return sorted(scored, key=lambda c: c.scores.overall, reverse=True)[:count]


def run(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
    """Write the job's best clip candidates, with their scores, to scored.json.

    Reads meta.json (ingest), signals.json (signals) and candidates.json
    (curate), scores the candidates with the weights of the job's genre
    (pipeline/genre) and keeps the settings.processing.num_clips with the
    highest overall score, best first; candidates with equal overall scores
    keep the order of candidates.json. Skips the work if scored.json exists,
    unless force. Raises StepError if an input is missing or not valid, or
    if cfg.score_weights cannot weigh the genre's clips.
    """
    output = job_dir / SCORED
    if is_done(output, force=force):
        logger.info("%s exists; skipping score", output)
        settings.report_progress(1.0)
        return output
    output.unlink(missing_ok=True)

    meta = load_meta(job_dir)
    events = load_json(job_dir / SIGNALS, SignalList, "signals").root
    candidates = load_json(job_dir / CANDIDATES, CandidateList, "curate").clips
    genre = job_genre(job_dir, settings.processing, meta)
    weights = component_weights(genre, settings.cfg.score_weights)
    scored = [score_candidate(c, events, weights) for c in candidates]
    kept = rank(scored, settings.processing.num_clips)
    write_json(output, ScoredList(clips=kept))
    settings.report_progress(1.0)
    logger.info(
        "kept the best %d of %d candidates; %s weights: %s",
        len(kept),
        len(candidates),
        genre,
        ", ".join(f"{name} {weights[name]:.2f}" for name in COMPONENTS),
    )
    for c in kept:
        logger.info(
            "%.1f-%.1fs overall %d (llm %.2f, laugh %.2f, energy %.2f): %r",
            c.start,
            c.end,
            c.scores.overall,
            llm_average(c) / MAX_SCORE,
            c.scores.laugh,
            c.scores.energy,
            c.title,
        )
    return output
