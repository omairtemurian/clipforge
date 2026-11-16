"""Tests of the lines of enriched.txt (SPEC 6.4): their timestamps and text,
where the laugh, applause and scene-cut markers go in them, and how curate
reads their starts back."""

from collections.abc import Sequence
from typing import Any

import pytest
from builders import cut, event, segment, word
from clipforge.models import Segment, SignalEvent, Transcript, Word
from clipforge.pipeline.enrich import (
    PromptLine,
    enriched_lines,
    marker,
    parse_line,
    text_pieces,
    timestamp,
)
from fakes import FIXTURES

TWO = [
    segment(0, "One two.", [10.0, 10.5], 11.0),
    segment(1, "Three four.", [13.0, 13.5], 14.0),
]


def texts(lines: Sequence[PromptLine]) -> list[str]:
    """Return the text after "SPEAKER: " of each line."""
    return [line.text.split(": ", 1)[1] for line in lines]


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "00:00.0"),
        (0.04, "00:00.0"),
        (1.41, "00:01.4"),
        (65.5, "01:05.5"),
        (59.96, "01:00.0"),
        (599.9, "09:59.9"),
        (3725, "62:05.0"),
    ],
)
def test_timestamps_are_minutes_and_seconds_with_one_decimal(
    seconds: float, text: str
) -> None:
    assert timestamp(seconds) == text


@pytest.mark.parametrize(
    ("signal", "text"),
    [
        (event("laugh", 13.85, 16.24, 0.853), "[LAUGH 2.4s 0.85]"),
        (event("laugh", 1.0, 1.44, 1.0), "[LAUGH 0.4s 1.00]"),
        (event("applause", 30.0, 33.0, 0.7), "[APPLAUSE 3.0s 0.70]"),
        (cut(12.0), "[SCENE CUT]"),
    ],
)
def test_markers_show_duration_with_one_decimal_and_intensity(
    signal: SignalEvent, text: str
) -> None:
    assert marker(signal) == text


@pytest.mark.parametrize(
    "signal", [event("silence", 10.8, 13.0), event("energy_peak", 12.0, 12.5, 0.6)]
)
def test_silences_and_energy_peaks_have_no_marker(signal: SignalEvent) -> None:
    with pytest.raises(KeyError):
        marker(signal)
    assert enriched_lines(TWO, [signal]) == enriched_lines(TWO, [])


@pytest.mark.parametrize(
    ("time", "first", "second"),
    [
        (9.0, "[SCENE CUT] One two.", "Three four."),
        (10.0, "[SCENE CUT] One two.", "Three four."),
        (10.2, "One [SCENE CUT] two.", "Three four."),
        (10.5, "One [SCENE CUT] two.", "Three four."),
        (12.0, "One two. [SCENE CUT]", "Three four."),
        (13.0, "One two. [SCENE CUT]", "Three four."),
        (13.6, "One two.", "Three four. [SCENE CUT]"),
        (20.0, "One two.", "Three four. [SCENE CUT]"),
    ],
)
def test_a_marker_follows_the_last_word_that_starts_before_its_event(
    time: float, first: str, second: str
) -> None:
    assert texts(enriched_lines(TWO, [cut(time)])) == [first, second]


def test_markers_at_one_place_are_in_order_of_start_then_kind() -> None:
    events = [cut(12.0), event("laugh", 12.0, 13.0, 0.5), event("applause", 11.5, 13.0)]
    assert texts(enriched_lines(TWO, events))[0] == (
        "One two. [APPLAUSE 1.5s 1.00] [LAUGH 1.0s 0.50] [SCENE CUT]"
    )


def test_a_word_without_a_leading_space_stays_in_its_piece_of_text() -> None:
    # Whisper splits "twenty-five" into the words "twenty" and "-five".
    words = [word("It", 1.0), word("was", 1.2), word("twenty", 1.5)]
    words += [word("-five", 1.9), word("dollars.", 2.3)]
    seg = Segment(
        id=0,
        start=1.0,
        end=2.8,
        text="It was twenty-five dollars.",
        words=words,
        speaker="S0",
    )

    assert text_pieces(seg) == [
        (1.0, "It"),
        (1.2, "was"),
        (1.5, "twenty-five"),
        (2.3, "dollars."),
    ]
    assert texts(enriched_lines([seg], [cut(1.7)])) == [
        "It was twenty-five [SCENE CUT] dollars."
    ]


@pytest.mark.parametrize(
    "words",
    [
        [word("Howdy", 1.2), word("there.", 1.8)],
        [word("Hello", 1.2)],
        [word("Hello", 1.2), word("there.", 1.8), word("Bye.", 2.5)],
        [],
    ],
)
def test_text_that_its_words_do_not_spell_is_one_piece(words: list[Word]) -> None:
    seg = Segment(
        id=0, start=1.0, end=3.0, text="Hello there.", words=words, speaker="S0"
    )

    assert text_pieces(seg) == [(1.0, "Hello there.")]
    assert texts(enriched_lines([seg], [cut(0.5), cut(1.0), cut(1.5)])) == [
        "[SCENE CUT] [SCENE CUT] Hello there. [SCENE CUT]"
    ]


def test_lines_collapse_whitespace_and_skip_segments_without_text() -> None:
    def wordless(start: float, end: float, text: str) -> Segment:
        return Segment(id=0, start=start, end=end, text=text, words=[], speaker="S1")

    segments = [
        wordless(61.25, 64, "  So \n what  now?"),
        wordless(64.5, 65, " \n "),
        wordless(70, 71, "Bye."),
    ]
    assert enriched_lines(segments, [cut(64.7)]) == [
        PromptLine(61.25, "[01:01.2-01:04.0] S1: So what now? [SCENE CUT]"),
        PromptLine(70, "[01:10.0-01:11.0] S1: Bye."),
    ]


def test_without_speech_there_are_no_lines_and_no_markers() -> None:
    assert enriched_lines([], [event("laugh", 2.95, 5.05, 0.85), cut(1.0)]) == []


def test_the_fixture_laughs_end_the_lines_of_their_punchlines(
    expected: dict[str, Any],
) -> None:
    transcript = Transcript.model_validate_json(
        (FIXTURES / "transcript.json").read_bytes()
    )
    laughs = [event("laugh", x["start"], x["end"], 0.8) for x in expected["laughs"]]

    plain = enriched_lines(transcript.segments, [])
    lines = enriched_lines(transcript.segments, laughs)

    assert texts(plain) == [seg.text for seg in transcript.segments]
    assert plain[0] == PromptLine(0.5, "[00:00.5-00:01.4] S0: Hi everyone.")
    marked = {3: "[LAUGH 2.5s 0.80]", 7: "[LAUGH 2.0s 0.80]", 10: "[LAUGH 3.0s 0.80]"}
    assert [line.text for line in lines] == [
        f"{line.text} {marked[index]}" if index in marked else line.text
        for index, line in enumerate(plain)
    ]


@pytest.mark.parametrize(
    ("text", "start"),
    [
        ("[00:00.5-00:01.4] S0: Hi everyone.", 0.5),
        ("[01:05.5-01:09.0] S1: Yes. [LAUGH 2.1s 0.85]", 65.5),
        ("[09:59.9-10:02.0] S0: Ten minutes in.", 599.9),
        ("[62:05.0-62:07.5] S0: Over an hour in.", 3725),
    ],
)
def test_parse_line_reads_the_start_of_a_line(text: str, start: float) -> None:
    assert parse_line(text) == PromptLine(start, text)


@pytest.mark.parametrize(
    "text",
    [
        "Hi everyone.",
        "",
        " [00:00.5-00:01.4] S0: Hi.",
        "[0:00.5-00:01.4] S0: Hi.",
        "[00:60.0-01:00.4] S0: Hi.",
        "[00:00-00:01] S0: Hi.",
    ],
)
def test_parse_line_rejects_text_that_does_not_start_with_a_time(text: str) -> None:
    with pytest.raises(ValueError, match=r'does not start with "\[mm:ss\.s-"'):
        parse_line(text)


def test_parse_line_reads_back_each_start_to_a_tenth_of_a_second() -> None:
    transcript = Transcript.model_validate_json(
        (FIXTURES / "transcript.json").read_bytes()
    )
    lines = enriched_lines(transcript.segments, [cut(20.0)])
    starts = [parse_line(line.text).start for line in lines]
    # Rounding to 0.1 s moves a start by up to 0.05 s: 3.45 s shows as 00:03.4.
    assert starts == pytest.approx([line.start for line in lines], abs=0.05 + 1e-9)
