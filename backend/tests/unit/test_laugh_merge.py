"""Tests of how scored frames become laugh and applause events (SPEC 6.3).

merge_active_frames and intensity (pipeline/signal_merge) are pure; the
numbers here are worked out by hand. frame_spans and signal_event
(pipeline/signals) put YAMNet frames on the time line and rate an event by
an RMS envelope (pipeline/loudness).
"""

import numpy as np
import pytest
from clipforge.config import Settings
from clipforge.models import SignalEvent
from clipforge.pipeline.loudness import Envelope
from clipforge.pipeline.signal_merge import ScoredSpan, intensity, merge_active_frames
from clipforge.pipeline.signals import ACTIVE_SCORE, frame_spans, signal_event

CFG = Settings()


def frames(*scores: float, hop: float = 0.25) -> list[ScoredSpan]:
    """Return back-to-back frames of hop seconds from time 0 with scores."""
    return [ScoredSpan(i * hop, (i + 1) * hop, s) for i, s in enumerate(scores)]


def merge(spans: list[ScoredSpan]) -> list[ScoredSpan]:
    """Merge spans as the signals do with the default settings."""
    return merge_active_frames(
        spans,
        threshold=ACTIVE_SCORE,
        max_gap=CFG.laugh_merge_gap_s,
        min_duration=CFG.laugh_min_duration_s,
    )


def test_defaults_are_those_of_the_spec() -> None:
    assert (ACTIVE_SCORE, CFG.laugh_merge_gap_s, CFG.laugh_min_duration_s) == (
        0.3,
        0.75,
        0.4,
    )


def test_active_frames_0_75_s_apart_merge_into_one_event() -> None:
    # Active 0-0.5 s and 1.25-1.75 s: a gap of exactly 0.75 s.
    spans = frames(0.5, 0.75, 0.0, 0.1, 0.2, 1.0, 0.75)
    assert merge(spans) == [ScoredSpan(0.0, 1.75, 0.75)]


def test_active_frames_more_than_0_75_s_apart_are_separate_events() -> None:
    # Active 0-0.5 s and 1.5-2 s: a gap of 1 s.
    spans = frames(0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.75, 0.75)
    assert merge(spans) == [ScoredSpan(0.0, 0.5, 0.5), ScoredSpan(1.5, 2.0, 0.75)]


def test_events_shorter_than_0_4_s_are_dropped() -> None:
    # A 0.25 s event, 1 s of quiet, then a 0.5 s event.
    spans = frames(0.5, 0.0, 0.0, 0.0, 0.0, 0.5, 0.5)
    assert merge(spans) == [ScoredSpan(1.25, 1.75, 0.5)]
    assert merge(frames(0.5, 0.5, hop=0.2)) == [ScoredSpan(0.0, 0.4, 0.5)]
    assert merge(frames(0.5, hop=0.39)) == []


def test_a_frame_must_score_above_0_3_to_be_active() -> None:
    assert merge(frames(0.3, 0.3, 0.3)) == []
    assert merge(frames(0.25, 0.375, 0.375)) == [ScoredSpan(0.25, 0.75, 0.375)]


def test_event_score_is_the_mean_score_of_its_active_frames() -> None:
    # The quiet frame in the middle is part of the event but not of its score.
    assert merge(frames(0.5, 0.0, 1.0)) == [ScoredSpan(0.0, 0.75, 0.75)]


def test_no_frames_make_no_events() -> None:
    assert merge([]) == []


def test_yamnet_frame_i_stands_for_the_middle_of_its_window() -> None:
    spans = frame_spans(10.0, np.array([0.25, 0.5], dtype=np.float32), 100.0)
    assert [(s.start, s.end, s.score) for s in spans] == [
        pytest.approx((10.24, 10.72, 0.25)),
        pytest.approx((10.72, 11.2, 0.5)),
    ]


def test_on_the_yamnet_grid_one_quiet_frame_is_bridged_but_not_two() -> None:
    spans = frame_spans(0.0, [0.9, 0.1, 0.9, 0.1, 0.1, 0.9], 100.0)
    events = [(e.start, e.end, e.score) for e in merge(spans)]
    assert events == [
        pytest.approx((0.24, 1.68, 0.9)),
        pytest.approx((2.64, 3.12, 0.9)),
    ]


def test_frames_are_cut_at_the_end_of_the_timeframe() -> None:
    spans = frame_spans(0.0, [0.9, 0.9, 0.9], 1.0)
    assert [(s.start, s.end) for s in spans] == [
        pytest.approx((0.24, 0.72)),
        pytest.approx((0.72, 1.0)),
    ]
    # An event cut to 0.26 s by the end of the timeframe is too short.
    assert merge(frame_spans(0.0, [0.9], 0.5)) == []


@pytest.mark.parametrize(
    ("score", "level", "baseline", "expected"),
    [
        (0.8, -20.0, -26.0, 0.4),
        (1.0, -23.0, -26.0, 0.25),
        (0.8, -14.0, -26.0, 0.8),
        (0.8, 0.0, -26.0, 0.8),
        (0.8, -26.0, -26.0, 0.0),
        (0.8, -30.0, -26.0, 0.0),
    ],
)
def test_intensity_is_the_score_scaled_by_the_level_over_the_baseline(
    score: float, level: float, baseline: float, expected: float
) -> None:
    assert intensity(score, level, baseline) == pytest.approx(expected)


def test_event_intensity_compares_its_level_with_the_rolling_median() -> None:
    # 30 s at -40 dB with the frames centered in 10-12 s at -30 dB: the
    # event is 10 dB above the median of the 30 s around it.
    levels = np.full(3000, -40.0, dtype=np.float32)
    levels[999:1199] = -30.0
    envelope = Envelope(0.0, levels)
    event = signal_event("laugh", ScoredSpan(10.0, 12.0, 0.6), envelope)
    assert event == SignalEvent(kind="laugh", start=10.0, end=12.0, intensity=0.5)


def test_event_where_the_envelope_has_no_frames_has_intensity_0() -> None:
    envelope = Envelope(0.0, np.zeros(0, dtype=np.float32))
    span = ScoredSpan(3.6000000000000005, 4.0800000000000001, 0.9)
    event = signal_event("applause", span, envelope)
    assert event == SignalEvent(kind="applause", start=3.6, end=4.08, intensity=0.0)
