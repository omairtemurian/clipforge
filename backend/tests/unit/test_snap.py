"""Tests for snapping clips between words (SPEC 6.7) on the fixture transcript.

The fixture's words open a phrase at its 14 segment starts and after 7
pauses of at least 0.35 s (decisions.md, TASK-7), and its laughs are at
14.16-16.08, 33.36-34.8 and 52.08-54.48 s (FIXTURE_LAUGHS).
"""

import random
from collections.abc import Sequence

import pytest
from builders import FIXTURE_LAUGHS, event, word
from clipforge.models import (
    CandidateList,
    ScoredCandidate,
    Scores,
    Segment,
    SignalEvent,
    Transcript,
)
from clipforge.pipeline import snap
from fakes import FIXTURES, LLM_RESPONSE

TRANSCRIPT = Transcript.model_validate_json((FIXTURES / "transcript.json").read_bytes())
WORDS = snap.spoken_words(TRANSCRIPT.segments)
# The end of the fixture's timeframe: the whole 60 s video.
END = 60.0
# Words that follow a pause of 0.35 s or more without starting a segment.
AFTER_PAUSES = [7.7, 11.1, 24.3, 30.65, 43.0, 46.4, 49.35]
_, A, *_ = CandidateList.model_validate_json(LLM_RESPONSE.read_bytes()).clips
CLIP = ScoredCandidate(
    **A.model_dump(),
    scores=Scores(
        overall=71, hook=88, flow=85, value=80, trend=75, laugh=0.8, energy=0
    ),
)


def snapped(
    start: float,
    end: float,
    *,
    comedy: bool = False,
    events: Sequence[SignalEvent] = FIXTURE_LAUGHS,
    limit: float = END,
) -> tuple[float, float] | None:
    """Return the start and end that snap gives a fixture clip from start to
    end seconds, or None if it drops the clip."""
    clip = CLIP.model_copy(update={"start": start, "end": end})
    moved = snap.snap_clip(clip, WORDS, events, comedy=comedy, limit=limit)
    return None if moved is None else (moved.start, moved.end)


def test_words_open_a_phrase_at_segment_starts_and_after_pauses() -> None:
    segment_starts = [segment.words[0].start for segment in TRANSCRIPT.segments]

    assert len(WORDS) == sum(len(s.words) for s in TRANSCRIPT.segments) == 104
    assert [w.start for w in WORDS if w.opens] == sorted(segment_starts + AFTER_PAUSES)
    assert [(w.start, w.end) for w in WORDS[:3]] == [
        (0.5, 0.75),
        (0.79, 1.41),
        (1.53, 1.78),
    ]


def test_a_pause_opens_a_phrase_from_0_35_s_to_the_millisecond() -> None:
    # 4.6 - 4.25 is 0.34999999999999964 and 5.299 - 4.95 is 0.349.
    words = [word("a", 0.0, 4.25), word("b", 4.6, 4.95), word("c", 5.299, 5.5)]
    segment = Segment(id=0, start=0.0, end=5.5, text="a b c", words=words, speaker="S0")

    assert [w.opens for w in snap.spoken_words([segment])] == [True, True, False]


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        # The starts of A and E, D and B: the segments 0, 1 and 4 start there.
        (0.5, 0.5),
        (1.5, 1.53),
        (16.9, 16.9),
        # "So," begins segment 1, only 0.12 s after "everyone.".
        (1.8, 1.53),
        # "So," starts exactly 0.3 s before 1.83: at the edge, which counts.
        (1.83, 1.53),
        # "So," starts 0.31 s before: "The" begins segment 2.
        (1.84, 3.45),
        # "so" follows "Um," after 0.55 s, inside segment 3.
        (7.9, 7.7),
        # "I listened, and my body said," go on with the phrase; "why"
        # follows a 0.6 s pause.
        (8.3, 11.1),
    ],
)
def test_a_clip_starts_with_the_first_word_that_opens_a_phrase(
    start: float, expected: float
) -> None:
    # The end: "cheese." ends at 32.85, plus 0.3 s.
    assert snapped(start, 35.2) == (expected, 33.15)


def test_a_clip_starts_up_to_0_3_s_early_to_the_millisecond() -> None:
    # 36.1 - 0.3 is 35.800000000000004: "My" (35.8) still starts at or after
    # it. "goodnight!" ends at 59.5, plus 0.3 s.
    assert snapped(36.1, 59.5) == (35.8, 59.8)


def test_without_an_opening_word_a_clip_starts_with_its_first_word() -> None:
    # 8.0-10.0 s: "I listened, and my body" continue "so"'s phrase; "body"
    # (9.65-10.05) is cut whole and its tail stops where "said," starts.
    assert snapped(8.3, 10.0) == (8.01, 10.09)


@pytest.mark.parametrize(
    ("start", "end"),
    [(13.6, 16.5), (49.7, 50.1), (59.6, 60.0)],
)
def test_a_clip_in_which_no_word_starts_is_dropped(start: float, end: float) -> None:
    # The first laugh, inside "recalculating" (49.35-50.22), after "goodnight!".
    assert snapped(start, end) is None


@pytest.mark.parametrize(
    ("end", "comedy", "expected"),
    [
        # "floor?" (12.99-13.5) is the last word before 13.6 and before 13.2.
        (13.6, False, 13.8),
        (13.2, False, 13.8),
        # The laugh after it ends at 16.08, more than 1.5 s later.
        (13.6, True, 15.0),
        (13.2, True, 15.0),
        # "floor?" starts at the end: "the" ends at 12.95 and its tail stops
        # where "floor?" starts.
        (12.99, False, 12.99),
        # No laugh follows "body." (5.72-6.05): comedy gets 0.3 s too.
        (6.2, True, 6.35),
        # The tail of "everyone." stops where "So," starts, 0.12 s later.
        (1.45, False, 1.53),
        # The ends of A ("cheese." 32.85), B ("choices." 51.55) and C
        # ("goodnight!" 59.5).
        (35.2, True, 34.35),
        (35.2, False, 33.15),
        (54.9, True, 53.05),
        (54.9, False, 51.85),
        (59.5, True, 59.8),
    ],
)
def test_a_clip_ends_after_its_last_word_with_a_tail(
    end: float, comedy: bool, expected: float
) -> None:
    assert snapped(0.5, end, comedy=comedy) == (0.5, expected)


@pytest.mark.parametrize(
    ("laugh", "expected"),
    [
        # It ends 0.7 s after "floor?" (12.99-13.5) ends.
        ((13.6, 14.2), 14.2),
        # It starts during "floor?".
        ((13.0, 13.7), 13.7),
        # It starts 1.5 s after "floor?": the tail reaches it, but no further.
        ((15.0, 16.0), 15.0),
        # It starts too late, or ends with the word: no laugh tail.
        ((15.01, 16.0), 13.8),
        ((12.0, 13.5), 13.8),
    ],
)
def test_a_comedy_tail_lasts_until_the_laugh_after_the_last_word_ends(
    laugh: tuple[float, float], expected: float
) -> None:
    events = [event("laugh", *laugh)]

    assert snapped(11.1, 13.6, comedy=True, events=events) == (11.1, expected)


def test_only_laughs_lengthen_a_comedy_tail() -> None:
    events = [event("applause", 13.6, 14.6), event("energy_peak", 13.0, 15.0)]

    assert snapped(11.1, 13.6, comedy=True, events=events) == (11.1, 13.8)


def test_a_comedy_tail_stops_where_the_next_word_starts() -> None:
    events = [event("laugh", 1.0, 2.5)]

    assert snapped(0.5, 1.45, comedy=True, events=events) == (0.5, 1.53)


@pytest.mark.parametrize(
    ("limit", "comedy", "expected"),
    [(13.7, False, 13.7), (14.0, True, 14.0), (13.3, False, 13.5)],
)
def test_a_tail_stops_at_the_end_of_the_timeframe(
    limit: float, comedy: bool, expected: float
) -> None:
    # A limit inside "floor?" (12.99-13.5) does not cut it.
    assert snapped(11.1, 13.2, comedy=comedy, limit=limit) == (11.1, expected)


def test_snap_keeps_the_rest_of_the_clip() -> None:
    clip = CLIP.model_copy(update={"start": 1.8, "end": 13.6})

    moved = snap.snap_clip(clip, WORDS, FIXTURE_LAUGHS, comedy=True, limit=END)

    assert moved is not None
    assert (moved.start, moved.end) == (1.53, 15.0)
    assert moved.model_dump(exclude={"start", "end"}) == clip.model_dump(
        exclude={"start", "end"}
    )


def inside_a_word(time: float) -> bool:
    """Return True if time falls strictly inside a word of the fixture."""
    return any(w.start < time < w.end for w in WORDS)


@pytest.mark.parametrize("comedy", [True, False])
def test_no_snapped_clip_starts_or_ends_inside_a_word(comedy: bool) -> None:
    rng = random.Random(20261031)
    starts = {w.start for w in WORDS}
    kept = 0
    for _ in range(1000):
        start = round(rng.uniform(0.0, END - 0.1), 2)
        end = round(rng.uniform(start + 0.1, END), 2)
        result = snapped(start, end, comedy=comedy)
        if result is None:
            assert all(w.start < start - 0.3 - 1e-9 or w.start >= end for w in WORDS)
            continue
        kept += 1
        new_start, new_end = result
        assert not inside_a_word(new_start) and not inside_a_word(new_end)
        assert new_start in starts
        assert start - 0.3 - 1e-9 <= new_start < end
        assert new_start < new_end <= END
    assert kept > 900
