"""Tests of polish (SPEC 6.10): filler cuts, cut spans and re-timed captions."""

import shutil
from pathlib import Path

import pytest
from builders import FIXTURE_LAUGHS, event, said, word
from clipforge.models import CutRange, Segment, SignalEvent, SignalList, Transcript
from clipforge.pipeline.caption_lines import CaptionWord, clip_words
from clipforge.pipeline.frame_cuts import Span, cut_spans, output_ms, retime
from clipforge.pipeline.polish import (
    filler_cuts,
    is_filler,
    load_filler_cuts,
    spoken_pieces,
)
from clipforge.pipeline.step import SIGNALS, TRANSCRIPT, StepError, write_json
from fakes import FIXTURES

FIXTURE = Transcript.model_validate_json((FIXTURES / TRANSCRIPT).read_bytes())
# Clip A of the fixture, as snap moves it (0.5-34.35 s), and its filler cuts.
CLIP_A = (0.5, 34.35)
CUTS_A = [(6.2, 7.55), (22.6, 24.15)]


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        # "Um," (6.75-7.15) and "Like," (23.25-23.6), with the pauses around
        # them, 0.15 s from "body." / "hawk." to 0.15 s before "so" / "it".
        # The laughs after "floor?" and "cheese." and the 0.6 s gaps after
        # "said," stay.
        (*CLIP_A, CUTS_A),
        # Clip B: "Like," and "Uh," (42.1-42.45) from "home." to "it"; the
        # laugh after "choices." stays.
        (16.9, 53.05, [(22.6, 24.15), (41.5, 42.85)]),
        (35.8, 59.8, [(41.5, 42.85)]),
    ],
)
def test_filler_cuts_of_the_fixture_clips(
    start: float, end: float, expected: list[CutRange]
) -> None:
    assert filler_cuts(FIXTURE, FIXTURE_LAUGHS, start, end) == expected


def test_without_their_laughs_the_laugh_gaps_are_pauses() -> None:
    assert filler_cuts(FIXTURE, [], *CLIP_A) == [
        (6.2, 7.55),
        (13.65, 16.75),
        (22.6, 24.15),
        (33.0, 34.2),
    ]


def test_like_in_a_phrase_is_kept_and_like_between_pauses_is_a_filler() -> None:
    pieces = spoken_pieces(FIXTURE)

    likes = [
        (piece.start, is_filler(pieces, index))
        for index, piece in enumerate(pieces)
        if piece.key == "like"
    ]
    # "It watches me like a hawk." and "Like," after "hawk.".
    assert likes == [(21430, False), (23250, True)]


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [(0.35, 0.35, [(1.35, 2.05)]), (0.349, 0.5, []), (0.5, 0.349, [])],
)
def test_like_needs_silence_of_0_35_s_before_and_after_it(
    before: float, after: float, expected: list[CutRange]
) -> None:
    like_start = 1.2 + before
    it_start = like_start + 0.3 + after
    transcript = said(
        ("I", 1.0, 1.2), ("like", like_start, like_start + 0.3), ("it", it_start, 3.0)
    )

    assert filler_cuts(transcript, [], 1.0, 3.0) == expected


def test_no_word_before_or_after_like_counts_as_silence() -> None:
    first = said(("Like,", 0.0, 0.3), ("so", 0.65, 0.9))
    last = said(("so", 0.0, 0.2), ("like.", 0.55, 0.8))
    too_close = said(("Like,", 0.0, 0.3), ("so", 0.5, 0.9))

    assert filler_cuts(first, [], 0.0, 1.0) == [(0.0, 0.5)]
    assert filler_cuts(last, [], 0.0, 1.0) == [(0.35, 0.85)]
    assert filler_cuts(too_close, [], 0.0, 1.0) == []


def test_filler_keys_ignore_case_and_punctuation() -> None:
    texts = ["UM...", "Erm,", "ah!", "Uh", "Ah-ha", "umbrella", "liked"]
    pieces = spoken_pieces(said(*((t, n, n + 0.2) for n, t in enumerate(texts))))

    fillers = [is_filler(pieces, index) for index in range(len(pieces))]
    assert fillers == [True, True, True, True, False, False, False]


def test_words_spelling_one_caption_word_are_never_cut_in_half() -> None:
    words = [word("Um", 1.0, 1.2), word("-hmm,", 1.2, 1.5), word("sure.", 1.6, 2.0)]
    spoken = Segment(
        id=0, start=1.0, end=2.0, text="Um-hmm, sure.", words=words, speaker="S0"
    )
    transcript = Transcript(language="en", duration=60.0, segments=[spoken])

    assert filler_cuts(transcript, [], 1.0, 2.0) == []


@pytest.mark.parametrize(("gap", "expected"), [(0.6, []), (0.601, [(1.35, 1.651)])])
def test_only_pauses_of_more_than_0_6_s_are_cut(
    gap: float, expected: list[CutRange]
) -> None:
    transcript = said(("one", 1.0, 1.2), ("two", 1.2 + gap, 2.2 + gap))

    assert filler_cuts(transcript, [], 1.0, 2.2 + gap) == expected


@pytest.mark.parametrize(
    ("events", "expected"),
    [
        ([event("laugh", 1.5, 1.9)], []),
        ([event("applause", 1.9, 3.0)], []),
        # Events that are not reactions, or that only touch the gap.
        ([event("energy_peak", 1.3, 1.9), event("laugh", 0.5, 1.2)], [(1.35, 1.85)]),
    ],
)
def test_a_gap_during_a_laugh_or_applause_is_not_a_pause(
    events: list[SignalEvent], expected: list[CutRange]
) -> None:
    transcript = said(("one", 1.0, 1.2), ("two", 2.0, 2.3))

    assert filler_cuts(transcript, events, 1.0, 2.3) == expected


def test_fillers_outside_a_pause_are_cut_from_the_first_start_to_the_last_end() -> None:
    short_gap = said(
        ("so", 10.0, 10.3), ("uh,", 10.35, 10.45), ("um", 10.5, 10.6), ("we", 10.65, 11)
    )
    in_a_laugh = said(("one", 1.0, 1.2), ("uh", 1.5, 1.7), ("two", 2.0, 2.3))

    assert filler_cuts(short_gap, [], 10.0, 11.0) == [(10.35, 10.6)]
    assert filler_cuts(in_a_laugh, [event("laugh", 1.2, 2.0)], 1.0, 2.3) == [(1.5, 1.7)]


def test_the_clip_edges_bound_its_first_and_last_gaps() -> None:
    transcript = said(("Uh,", 0.0, 0.4), ("so", 1.2, 1.5), ("done.", 3.0, 3.2))

    assert filler_cuts(transcript, [], 0.0, 5.0) == [
        (0.0, 1.05),
        (1.65, 2.85),
        (3.35, 4.85),
    ]
    # Words that start outside the clip are neither cut nor kept words.
    assert filler_cuts(transcript, [], 1.2, 3.0) == [(1.65, 2.85)]


def test_cuts_never_reach_into_kept_words() -> None:
    transcript = said(("so", 10.0, 10.5), ("um", 10.4, 10.7), ("we", 10.75, 11.0))

    assert filler_cuts(transcript, [], 10.0, 11.0) == [(10.5, 10.7)]


def test_load_filler_cuts_reads_the_transcript_and_signals_of_a_job(
    tmp_path: Path,
) -> None:
    shutil.copyfile(FIXTURES / TRANSCRIPT, tmp_path / TRANSCRIPT)
    write_json(tmp_path / SIGNALS, SignalList(list(FIXTURE_LAUGHS)))

    assert load_filler_cuts(tmp_path, [CLIP_A, (35.8, 59.8)]) == [
        CUTS_A,
        [(41.5, 42.85)],
    ]
    (tmp_path / SIGNALS).unlink()
    with pytest.raises(StepError, match=r"signals\.json not found; run the signals"):
        load_filler_cuts(tmp_path, [CLIP_A])


def test_cut_spans_are_milliseconds_of_the_clip_in_order_and_merged() -> None:
    ranges = [
        (12.0, 12.5),
        (9.0, 10.2),
        (11.0, 11.5),
        (11.4, 11.8),
        (11.8, 11.9),
        (12.4, 12.4),
        (14.0, 15.0),
    ]

    assert cut_spans(10.0, 13.0, ranges) == [(0, 200), (1000, 1900), (2000, 2500)]
    assert cut_spans(10.0, 13.0, []) == []


@pytest.mark.parametrize(
    ("time", "expected"),
    [
        (0, 0),
        (1000, 1000),
        (1200, 1000),
        (1500, 1000),
        (2000, 1500),
        (3500, 2500),
        (4000, 2500),
        (5000, 3500),
    ],
)
def test_output_ms_takes_out_the_cut_time_before(time: int, expected: int) -> None:
    spans: list[Span] = [(1000, 1500), (3000, 4000)]

    assert output_ms(time, spans) == expected


def test_retime_moves_the_fixture_words_of_clip_a_after_its_cuts() -> None:
    words = clip_words(FIXTURE, *CLIP_A)
    keys = {"body.", "Um,", "so", "hawk.", "Like,", "it", "cheese."}

    retimed = retime(words, cut_spans(*CLIP_A, CUTS_A))

    assert len(words) - len(retimed) == 2
    # "so" and "hawk." come 1.35 s earlier, "it" and "cheese." 2.9 s; a cut
    # pause lasts 0.3 s ("body." -> "so", "hawk." -> "it").
    assert [(w.text, w.start, w.end) for w in retimed if w.text in keys] == [
        ("body.", 5220, 5550),
        ("so", 5850, 6120),
        ("hawk.", 20220, 20600),
        ("it", 20900, 21110),
        ("cheese.", 29030, 29450),
    ]


def test_retime_keeps_the_part_of_a_word_that_is_not_cut() -> None:
    words = [
        CaptionWord("long", 1000, 2000, emphasis=True),
        CaptionWord("cut", 2100, 2400),
        CaptionWord("after", 2600, 2900),
    ]

    assert retime(words, [(1500, 2500)]) == [
        CaptionWord("long", 1000, 1500, emphasis=True),
        CaptionWord("after", 1600, 1900),
    ]
    assert retime(words, []) == words
