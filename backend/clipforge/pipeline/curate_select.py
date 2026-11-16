"""Choosing which of the LLM's clip candidates curate keeps (SPEC 6.5).

A candidate is dropped when it fails validate_candidate or lies outside the
project's timeframe. Of two candidates that overlap with an IoU above 0.5,
the one with the higher LLM average is kept. At most cfg.max_clips_from_llm
candidates are kept, the best first.
"""

import logging
from collections.abc import Iterable

from clipforge.candidate_rules import validate_candidate
from clipforge.config import Settings
from clipforge.models import ClipCandidate, ProcessingSettings, SourceMeta

logger = logging.getLogger(__name__)

# Candidates that overlap more than this (intersection over union) are
# duplicates.
DUPLICATE_IOU = 0.5
# Prompt timestamps are rounded to 0.1 s (SPEC 6.4), so a time the LLM takes
# from the first or last line can lie this far outside the timeframe.
PROMPT_ROUNDING_S = 0.05


def llm_average(c: ClipCandidate) -> float:
    """Return the mean of the candidate's hook, flow, value and trend scores."""
    return (c.hook + c.flow + c.value + c.trend) / 4


def iou(a: ClipCandidate, b: ClipCandidate) -> float:
    """Return the intersection over union of two candidates' time ranges.

    Overlap and union are rounded to milliseconds, the precision of
    timestamps, so float noise cannot lift an IoU of exactly 0.5 above it.
    """
    overlap = round(min(a.end, b.end) - max(a.start, b.start), 3)
    if overlap <= 0:
        return 0.0
    return overlap / round(max(a.end, b.end) - min(a.start, b.start), 3)


def fit_timeframe(c: ClipCandidate, meta: SourceMeta) -> ClipCandidate:
    """Move a start or end just outside the timeframe onto its bound.

    Only times at most PROMPT_ROUNDING_S outside are moved: those are
    timestamps of the first or last line that rounding pushed out.
    """
    start, end = c.start, c.end
    if 0 < round(meta.timeframe_start - start, 3) <= PROMPT_ROUNDING_S:
        start = meta.timeframe_start
    if 0 < round(end - meta.timeframe_end, 3) <= PROMPT_ROUNDING_S:
        end = meta.timeframe_end
    if (start, end) == (c.start, c.end):
        return c
    return c.model_copy(update={"start": start, "end": end})


def check_candidate(
    c: ClipCandidate, meta: SourceMeta, processing: ProcessingSettings, cfg: Settings
) -> tuple[bool, str]:
    """Check a candidate against the video, its length presets and the timeframe.

    Returns (True, "") to keep it, or (False, reason) to drop it.
    """
    ok, reason = validate_candidate(
        c, meta.duration, processing.length_presets, cfg, processing.custom_length
    )
    if ok and not (meta.timeframe_start <= c.start and c.end <= meta.timeframe_end):
        span = f"{meta.timeframe_start:g}-{meta.timeframe_end:g}s"
        return False, f"{c.start:g}-{c.end:g}s is outside the timeframe {span}"
    return ok, reason


def dedupe(candidates: Iterable[ClipCandidate]) -> list[ClipCandidate]:
    """Drop candidates that duplicate a better one; return the rest, best first.

    Candidates are taken by LLM average, highest first (equal averages keep
    their order), and one is kept unless its IoU with a kept candidate is
    above DUPLICATE_IOU.
    """
    kept: list[ClipCandidate] = []
    for c in sorted(candidates, key=llm_average, reverse=True):
        twin = next((k for k in kept if iou(c, k) > DUPLICATE_IOU), None)
        if twin is None:
            kept.append(c)
        else:
            logger.info(
                "dropped candidate %r: it repeats %r (IoU %.2f)",
                c.title,
                twin.title,
                iou(c, twin),
            )
    return kept


def select_candidates(
    candidates: Iterable[ClipCandidate],
    meta: SourceMeta,
    processing: ProcessingSettings,
    cfg: Settings,
) -> list[ClipCandidate]:
    """Return the candidates curate keeps, best LLM average first.

    Drops candidates that fail check_candidate (each drop is logged with its
    reason) and duplicates (dedupe), then keeps the best
    cfg.max_clips_from_llm.
    """
    valid = []
    for candidate in candidates:
        c = fit_timeframe(candidate, meta)
        ok, reason = check_candidate(c, meta, processing, cfg)
        if ok:
            valid.append(c)
        else:
            logger.info("dropped candidate %r: %s", c.title, reason)
    kept = dedupe(valid)
    if len(kept) > cfg.max_clips_from_llm:
        logger.info(
            "keeping the best %d of %d candidates", cfg.max_clips_from_llm, len(kept)
        )
    return kept[: cfg.max_clips_from_llm]
