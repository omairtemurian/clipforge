"""Pure helpers of the signals (SPEC 6.3): scored frames -> events.

A detector scores frames of the audio. The frames that score above a
threshold are active, and active frames close together form one event
(merge_active_frames). intensity rates an event by its score and by how much
louder it is than the audio around it. per_second_scores keeps a class's
scores as one number per second, and CROWD_KINDS are the events that a
clip's energy counts besides energy peaks (score.energy_score).
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import fmean

# Frame times are sums of float hops, so comparisons of durations and gaps
# allow this much rounding error (seconds).
EPSILON_S = 1e-6
# An event this many dB louder than its baseline gets its full score.
FULL_LOUDNESS_DB = 12.0
# The audience reactions that raise a clip's energy like an energy peak does.
CROWD_KINDS = frozenset({"applause", "cheer"})


@dataclass(frozen=True)
class ScoredSpan:
    """The time span [start, end] (seconds) of a frame or event, and its score."""

    start: float
    end: float
    score: float


def merge_active_frames(
    frames: Iterable[ScoredSpan],
    *,
    threshold: float,
    max_gap: float,
    min_duration: float,
) -> list[ScoredSpan]:
    """Return the events that the active frames among frames form.

    frames are in time order. A frame is active if its score is above
    threshold. An active frame joins the event of the active frame before it
    if the gap between them (its start minus that frame's end) is at most
    max_gap; the inactive frames in such a gap become part of the event. An
    event spans from the start of its first active frame to the end of its
    last one, and its score is the mean score of its active frames. Events
    shorter than min_duration are dropped.
    """
    runs: list[list[ScoredSpan]] = []
    for frame in frames:
        if frame.score <= threshold:
            continue
        if runs and frame.start - runs[-1][-1].end <= max_gap + EPSILON_S:
            runs[-1].append(frame)
        else:
            runs.append([frame])
    events = [
        ScoredSpan(run[0].start, run[-1].end, fmean(f.score for f in run))
        for run in runs
    ]
    return [e for e in events if e.end - e.start >= min_duration - EPSILON_S]


def intensity(score: float, level_db: float, baseline_db: float) -> float:
    """Return the intensity (0..1) of an event (SPEC 6.3).

    It is score * clamp((level_db - baseline_db) / 12, 0, 1): the event's
    mean class score, scaled by how far its level rises above the baseline
    level, in full from 12 dB above it and not at all if it is not louder.
    """
    loudness = min(max((level_db - baseline_db) / FULL_LOUDNESS_DB, 0.0), 1.0)
    return min(max(score * loudness, 0.0), 1.0)


def per_second_scores(
    frames: Iterable[ScoredSpan], start: float, end: float
) -> list[float]:
    """Return the highest score in each whole second of [start, end].

    Entry i covers [start + i, start + i + 1), the last one cut at end: it
    holds the highest score of the frames that overlap it, 0 if none does.
    There are ceil(end - start) entries, none if end <= start.
    """
    seconds = max(math.ceil(end - start - EPSILON_S), 0)
    scores = [0.0] * seconds
    for frame in frames:
        first = max(math.floor(frame.start - start + EPSILON_S), 0)
        last = min(math.ceil(frame.end - start - EPSILON_S), seconds)
        for second in range(first, last):
            scores[second] = max(scores[second], frame.score)
    return scores
