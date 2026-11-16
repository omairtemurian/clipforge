"""Tests of auto zoom (TASK-23): the punch-ins of a clip."""

from pathlib import Path

import pytest
from builders import FIXTURE_LAUGHS, event, said
from clipforge.models import ProcessingSettings, SignalList, Transcript, ZoomKeyframe
from clipforge.pipeline.auto_zoom import (
    EMPHASIS_SCALE,
    REACTION_SCALE,
    SENTENCE_SCALE,
    auto_zoom_keyframes,
    new_clip_zooms,
    punch_ins,
    zoom_triggers,
)
from clipforge.pipeline.step import SIGNALS, TRANSCRIPT, StepError, write_json
from fakes import FIXTURES

FIXTURE = Transcript.model_validate_json((FIXTURES / TRANSCRIPT).read_bytes())
TALK = said(
    ("I", 1.0, 1.2),
    ("love", 1.3, 1.6),
    ("pizza.", 1.7, 2.2),
    ("So", 3.0, 3.3),
    ("anyway", 3.4, 3.8),
    ("pizza", 7.0, 7.4),
    ("rules.", 7.5, 8.0),
)
EVENTS = [
    event("laugh", 9.0, 10.0),
    event("applause", 5.0, 6.0),
    event("energy_peak", 20.0, 21.0),
]


def zooms(keyframes: list[ZoomKeyframe]) -> list[tuple[float, float]]:
    """Return keyframes as (t, scale) pairs."""
    return [(keyframe.t, keyframe.scale) for keyframe in keyframes]


def test_triggers_are_emphasis_new_sentences_and_reactions_in_time_order() -> None:
    # "pizza" twice (emphasis), "So" after the cut of 2.2-3.0 s (the applause
    # keeps 3.8-7.0 s and the laugh 8.0-12.0 s), the laugh; the applause and
    # the energy peak after the clip are not triggers.
    assert zoom_triggers(TALK, EVENTS, ["pizza"], 0.5, 12.0, 0.5) == [
        (1700, EMPHASIS_SCALE),
        (2880, SENTENCE_SCALE),
        (7000, EMPHASIS_SCALE),
        (9000, REACTION_SCALE),
    ]
    # A run of emphasis words is one trigger, at its first word; at the
    # same time, the larger scale comes first.
    peak = [event("energy_peak", 1.7, 2.0)]
    assert zoom_triggers(TALK, peak, ["love pizza"], 0.5, 2.5, 5.0) == [
        (1300, EMPHASIS_SCALE),
        (1700, REACTION_SCALE),
    ]
    peak_first = [event("energy_peak", 1.3, 2.0)]
    assert zoom_triggers(TALK, peak_first, ["love"], 0.5, 2.5, 5.0) == [
        (1300, EMPHASIS_SCALE),
        (1300, REACTION_SCALE),
    ]


def test_punch_ins_ramp_in_hold_and_ease_back_at_least_3_s_apart() -> None:
    keyframes = punch_ins(
        zoom_triggers(TALK, EVENTS, ["pizza"], 0.5, 12.0, 0.5), 0.5, 12.0
    )

    # 2.88 and 9.0 are within 3 s of the emphasis punch-ins at 1.7 and 7.0.
    assert zooms(keyframes) == [
        (1.5, 1.0),
        (1.7, 1.15),
        (3.7, 1.15),
        (4.2, 1.0),
        (6.8, 1.0),
        (7.0, 1.15),
        (9.0, 1.15),
        (9.5, 1.0),
    ]


def test_punch_ins_take_the_larger_scale_first_then_time_order() -> None:
    triggers = [(2000, 1.12), (4000, 1.15), (6500, 1.13), (8000, 1.12)]
    # 4.0 (emphasis) first; the reaction at 6.5 and the sentence at 2.0 are
    # within 3 s of it; the sentence at 8.0 is not.
    assert zooms(punch_ins(triggers, 0.0, 20.0)) == [
        (3.8, 1.0),
        (4.0, 1.15),
        (6.0, 1.15),
        (6.5, 1.0),
        (7.8, 1.0),
        (8.0, 1.12),
        (10.0, 1.12),
        (10.5, 1.0),
    ]


@pytest.mark.parametrize(
    ("trigger", "end", "expected"),
    [
        # Too early to ramp in from the clip's start (0.5 s), then just enough.
        (600, 20.0, []),
        (700, 20.0, [(0.5, 1.0), (0.7, 1.13), (2.7, 1.13), (3.2, 1.0)]),
        # The hold shrinks to end by the clip's end, down to 1.5 s.
        (9000, 11.0, [(8.8, 1.0), (9.0, 1.13), (10.5, 1.13), (11.0, 1.0)]),
        (9000, 10.99, []),
    ],
)
def test_punch_ins_fit_inside_the_clip(
    trigger: int, end: float, expected: list[tuple[float, float]]
) -> None:
    assert zooms(punch_ins([(trigger, REACTION_SCALE)], 0.5, end)) == expected


def test_auto_zoom_keyframes_of_the_fixture_clip_a() -> None:
    keyframes = auto_zoom_keyframes(
        FIXTURE, FIXTURE_LAUGHS, ["cheese"], 0.5, 34.35, 0.5
    )

    # The new sentences after the auto cuts, and the laugh at 14.16 s;
    # "cheese." (32.43 s) is too close to the end to hold 1.5 s.
    punches = [(k.t, k.scale) for k in keyframes[1::4]]
    assert punches == [
        (3.33, 1.12),
        (6.63, 1.12),
        (10.98, 1.12),
        (14.16, 1.13),
        (20.13, 1.12),
        (23.13, 1.12),
        (27.53, 1.12),
        (30.53, 1.12),
    ]
    assert len(keyframes) == 32
    times = [keyframe.t for keyframe in keyframes]
    assert times == sorted(times)
    assert all(1.0 <= keyframe.scale <= 1.15 for keyframe in keyframes)


def test_new_clip_zooms_read_the_job_only_when_needed(tmp_path: Path) -> None:
    clips = [(0.5, 34.35, ["cheese"]), (35.8, 41.4, [])]
    off = ProcessingSettings(auto_zoom=False)
    assert new_clip_zooms(tmp_path, clips, off) == [[], []]
    assert new_clip_zooms(tmp_path, [], ProcessingSettings()) == []
    with pytest.raises(StepError, match=r"transcript\.json not found"):
        new_clip_zooms(tmp_path, clips, ProcessingSettings())
    (tmp_path / TRANSCRIPT).write_bytes((FIXTURES / TRANSCRIPT).read_bytes())
    write_json(tmp_path / SIGNALS, SignalList(list(FIXTURE_LAUGHS)))

    first, second = new_clip_zooms(tmp_path, clips, ProcessingSettings())

    assert len(first) == 32
    assert zooms(second) == [(38.63, 1.0), (38.83, 1.12), (40.83, 1.12), (41.33, 1.0)]
