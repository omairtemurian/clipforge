"""Tests of auto cut (TASK-27): jump cuts of the silences of a clip."""

from pathlib import Path

import pytest
from builders import FIXTURE_LAUGHS, event, said
from clipforge.models import CutRange, ProcessingSettings, SignalList, Transcript
from clipforge.pipeline.auto_cut import auto_cuts, merge_ranges, new_clip_cuts
from clipforge.pipeline.step import SIGNALS, TRANSCRIPT, StepError, write_json
from fakes import FIXTURES

FIXTURE = Transcript.model_validate_json((FIXTURES / TRANSCRIPT).read_bytes())
TALK = said(("Hi", 1.0, 1.4), ("there.", 1.5, 2.0), ("So", 3.0, 3.3))


def test_auto_cuts_take_out_the_silences_longer_than_the_min_pause() -> None:
    # 0.5 s before "Hi", 0.1 s after it, 1 s after "there.", 1.7 s after "So".
    assert auto_cuts(TALK, [], 0.5, 5.0, 0.5) == [(2.12, 2.88), (3.42, 4.88)]
    assert auto_cuts(TALK, [], 0.4, 5.0, 0.5) == [(0.52, 0.88), (2.12, 2.88)] + [
        (3.42, 4.88)
    ]
    assert auto_cuts(TALK, [], 0.5, 5.0, 1.0) == [(3.42, 4.88)]


def test_auto_cuts_keep_the_padding_and_the_audience_reactions() -> None:
    # A gap of 0.3 s is longer than 0.2 s but leaves nothing after padding.
    short = said(("One", 1.0, 1.5), ("two", 1.8, 2.2))
    assert auto_cuts(short, [], 1.0, 2.2, 0.2) == [(1.62, 1.68)]
    assert auto_cuts(short, [], 1.0, 2.2, 0.25) == [(1.62, 1.68)]
    tight = said(("One", 1.0, 1.5), ("two", 1.7, 2.2))
    assert auto_cuts(tight, [], 1.0, 2.2, 0.15) == []
    laugh = [event("laugh", 2.5, 2.8), event("energy_peak", 3.5, 4.0)]
    assert auto_cuts(TALK, laugh, 0.5, 5.0, 0.5) == [(3.42, 4.88)]


def test_auto_cuts_of_a_clip_without_words_cut_all_but_the_padding() -> None:
    assert auto_cuts(TALK, [], 10.0, 12.0, 0.5) == [(10.12, 11.88)]


def test_overlapping_words_leave_no_gap() -> None:
    overlap = said(("long", 1.0, 3.0), ("short", 1.5, 1.8), ("next", 3.1, 3.5))
    assert auto_cuts(overlap, [], 1.0, 3.5, 0.05) == []


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        # Clip A (0.5-34.35 s): the 0.55-0.8 s gaps between sentences and
        # around "Um," and "Like,"; the laughs after "floor?" (13.5-16.9) and
        # "cheese." (32.85-) stay.
        (
            0.5,
            34.35,
            [(3.02, 3.33), (6.17, 6.63), (7.27, 7.58), (10.62, 10.98)]
            + [(19.82, 20.13), (22.57, 23.13), (23.72, 24.18), (27.22, 27.53)]
            + [(30.17, 30.53)],
        ),
        (35.8, 41.4, [(38.52, 38.83)]),
    ],
)
def test_auto_cuts_of_the_fixture_clips(
    start: float, end: float, expected: list[CutRange]
) -> None:
    assert auto_cuts(FIXTURE, FIXTURE_LAUGHS, start, end, 0.5) == expected


def test_merge_ranges_sorts_and_merges_overlapping_or_touching_ranges() -> None:
    ranges = [(5.0, 6.0), (1.0, 2.0), (1.5, 3.0), (3.0, 4.0), (7.0, 8.0)]
    assert merge_ranges(ranges) == [(1.0, 4.0), (5.0, 6.0), (7.0, 8.0)]
    assert merge_ranges([]) == []


def test_new_clip_cuts_read_the_job_only_when_needed(tmp_path: Path) -> None:
    spans = [(0.5, 34.35), (35.8, 41.4)]
    off = ProcessingSettings(auto_cut=False)
    assert new_clip_cuts(tmp_path, spans, off) == [[], []]
    assert new_clip_cuts(tmp_path, [], ProcessingSettings()) == []
    with pytest.raises(StepError, match=r"transcript\.json not found"):
        new_clip_cuts(tmp_path, spans, ProcessingSettings())
    (tmp_path / TRANSCRIPT).write_bytes((FIXTURES / TRANSCRIPT).read_bytes())
    write_json(tmp_path / SIGNALS, SignalList(list(FIXTURE_LAUGHS)))

    longer = ProcessingSettings(auto_cut_min_pause_s=0.6)
    fillers = ProcessingSettings(remove_fillers=True, auto_cut=False)

    assert new_clip_cuts(tmp_path, spans, longer) == [
        [(6.17, 6.63), (22.57, 23.13), (23.72, 24.18)],
        [],
    ]
    assert new_clip_cuts(tmp_path, spans, fillers) == [
        [(6.2, 7.55), (22.6, 24.15)],
        [],
    ]
