"""Tests for choosing curate's clip candidates: checks, IoU dedupe and cap."""

import logging
from pathlib import Path

import pytest
from clipforge.config import Settings
from clipforge.models import (
    CandidateList,
    ClipCandidate,
    ProcessingSettings,
    SourceMeta,
)
from clipforge.pipeline.curate_select import (
    dedupe,
    fit_timeframe,
    iou,
    llm_average,
    select_candidates,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CFG = Settings(clip_min_s=20, clip_max_s=75, max_clips_from_llm=30)
AUTO = ProcessingSettings()
# llm_response.json: D, A, B, C, E. E is too short for "auto" (15.8 s), and D
# repeats A (IoU 0.905) with a lower LLM average (64 < 82).
D, A, B, C, E = CandidateList.model_validate_json(
    (FIXTURES / "llm_response.json").read_bytes()
).clips


def clip(start: float, end: float, score: int = 50, title: str = "") -> ClipCandidate:
    """Return a valid candidate with all four LLM scores set to score."""
    return A.model_copy(
        update={
            "start": start,
            "end": end,
            "title": title or f"{start:g}-{end:g}",
            "hook": score,
            "flow": score,
            "value": score,
            "trend": score,
        }
    )


def meta(duration: float = 60, start: float = 0) -> SourceMeta:
    """Return the meta of a video whose timeframe runs from start to its end."""
    return SourceMeta(
        title="sample",
        duration=duration,
        width=1280,
        height=720,
        fps=30,
        timeframe_start=start,
        timeframe_end=duration,
    )


def spans(candidates: list[ClipCandidate]) -> list[tuple[float, float]]:
    return [(c.start, c.end) for c in candidates]


def test_llm_average_is_the_mean_of_the_four_scores() -> None:
    assert llm_average(A) == 82.0
    assert llm_average(B) == 73.5


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((0, 10), (5, 15), 5 / 15),
        ((1.5, 32.9), (0.5, 35.2), 31.4 / 34.7),
        ((10, 20), (0, 40), 0.25),
        ((47.9, 77.9), (57.9, 87.9), 0.5),
        ((0.1, 0.8), (0.2, 1.3), 0.5),
        ((0, 10), (10, 20), 0.0),
        ((0, 10), (30, 40), 0.0),
        ((3, 9), (3, 9), 1.0),
    ],
)
def test_iou_exact_numbers(
    a: tuple[float, float], b: tuple[float, float], expected: float
) -> None:
    assert iou(clip(*a), clip(*b)) == expected
    assert iou(clip(*b), clip(*a)) == expected


def test_fixture_duplicate_pair_has_iou_0_905() -> None:
    assert iou(D, A) == 31.4 / 34.7
    assert round(iou(D, A), 3) == 0.905


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_dedupe_keeps_the_higher_llm_average(order: tuple[int, int]) -> None:
    low, high = clip(0, 30, score=60), clip(2, 31, score=70)
    pair = [(low, high)[i] for i in order]
    assert dedupe(pair) == [high]


def test_dedupe_keeps_an_overlap_of_exactly_one_half() -> None:
    first, second = clip(47.9, 77.9, score=70), clip(57.9, 87.9, score=60)
    assert dedupe([second, first]) == [first, second]


def test_dedupe_drops_an_overlap_just_above_one_half() -> None:
    # Overlap 20.1 s, union 39.9 s: IoU 0.504.
    first, second = clip(47.9, 78.0, score=70), clip(57.9, 87.8, score=60)
    assert dedupe([second, first]) == [first]


def test_dedupe_keeps_the_earlier_of_two_equal_averages() -> None:
    first, second = clip(0, 30, title="first"), clip(1, 30, title="second")
    assert dedupe([first, second]) == [first]
    assert dedupe([second, first]) == [second]


def test_dedupe_compares_with_kept_candidates_only() -> None:
    # b repeats a and is dropped; c overlaps b a lot but a only by 1/3.
    a, b, c = clip(0, 20, 90), clip(5, 25, 80), clip(10, 30, 70)
    assert dedupe([c, b, a]) == [a, c]


def test_select_fixture_candidates(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="clipforge.pipeline.curate_select"):
        kept = select_candidates([D, A, B, C, E], meta(), AUTO, CFG)
    assert kept == [A, B, C]
    assert f"dropped candidate {E.title!r}: length 15.8s is outside" in caplog.text
    assert f"dropped candidate {D.title!r}: it repeats {A.title!r}" in caplog.text


def test_select_applies_the_length_preset() -> None:
    lt30 = ProcessingSettings(length_presets=["lt30"])
    assert select_candidates([D, A, B, C, E], meta(), lt30, CFG) == [E, C]


def test_select_keeps_at_most_max_clips_from_llm() -> None:
    cfg = Settings(clip_min_s=20, clip_max_s=75, max_clips_from_llm=2)
    assert select_candidates([D, A, B, C, E], meta(), AUTO, cfg) == [A, B]


def test_select_drops_candidates_outside_the_timeframe(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="clipforge.pipeline.curate_select"):
        kept = select_candidates([A, B, C], meta(start=30), AUTO, CFG)
    assert kept == [C]
    assert "16.9-54.9s is outside the timeframe 30-60s" in caplog.text


def test_select_drops_candidates_after_the_video() -> None:
    late = clip(30, 60.1)
    assert select_candidates([late], meta(), AUTO, CFG) == []


@pytest.mark.parametrize(
    ("span", "fitted"),
    [
        ((30.0, 59.0), (30.04, 59.0)),
        ((31.0, 60.0), (31.0, 59.95)),
        ((30.0, 60.0), (30.04, 59.95)),
    ],
)
def test_times_rounded_out_of_the_timeframe_move_onto_it(
    span: tuple[float, float], fitted: tuple[float, float]
) -> None:
    # Prompt timestamps of 30.04 and 59.95 read 00:30.0 and 01:00.0.
    timeframe = meta(duration=59.95, start=30.04)
    candidate = clip(*span)
    assert spans([fit_timeframe(candidate, timeframe)]) == [fitted]
    assert spans(select_candidates([candidate], timeframe, AUTO, CFG)) == [fitted]


@pytest.mark.parametrize("span", [(29.9, 59.0), (31.0, 60.1), (31.0, 59.0)])
def test_times_further_out_or_inside_are_not_moved(span: tuple[float, float]) -> None:
    candidate = clip(*span)
    assert fit_timeframe(candidate, meta(duration=59.95, start=30.04)) is candidate
