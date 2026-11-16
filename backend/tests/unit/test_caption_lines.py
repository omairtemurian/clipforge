"""Tests of pipeline/caption_lines (SPEC 6.9): the words a clip's captions
show, how they break into lines, which of them are emphasis words, and how
long each one is the active word."""

from collections.abc import Sequence

import pytest
from builders import segment, word
from clipforge.models import Segment, Transcript
from clipforge.pipeline.caption_lines import (
    CaptionWord,
    active_end,
    clip_words,
    group_lines,
    line_break,
    mark_emphasis,
    to_ms,
    word_key,
)
from fakes import FIXTURES


def transcript(*segments: Segment) -> Transcript:
    """Return a transcript of segments."""
    return Transcript(language="en", duration=60, segments=list(segments))


def timed(words: Sequence[CaptionWord]) -> list[tuple[str, int, int]]:
    """Return the text, start and end of each word."""
    return [(word.text, word.start, word.end) for word in words]


def texts(lines: Sequence[Sequence[CaptionWord]]) -> list[list[str]]:
    """Return the texts of the words of each line."""
    return [[word.text for word in line] for line in lines]


def cw(text: str, start: int, end: int | None = None) -> CaptionWord:
    """Return a caption word that lasts until end, or else for 200 ms."""
    return CaptionWord(text, start, start + 200 if end is None else end)


def test_the_fixture_clip_shows_its_words_in_ms_from_its_start() -> None:
    fixture = Transcript.model_validate_json(
        (FIXTURES / "transcript.json").read_bytes()
    )

    assert timed(clip_words(fixture, 0.5, 3.0)) == [
        ("Hi", 0, 250),
        ("everyone.", 290, 910),
        ("So,", 1030, 1280),
        ("I", 1320, 1510),
        ("tried", 1550, 1990),
        ("yoga.", 2030, 2400),
    ]


def test_words_that_start_in_the_clip_show_and_end_by_its_end() -> None:
    # one 9.9-10, two 10-12.4, three 12.4-12.5, four 12.5-13.
    seg = segment(0, "one two three four", [9.9, 10.0, 12.4, 12.5], 13.0)

    assert timed(clip_words(transcript(seg), 10.0, 12.45)) == [
        ("two", 0, 2400),
        ("three", 2400, 2450),
    ]


def test_a_word_without_a_leading_space_joins_the_word_before_it() -> None:
    # Whisper splits "twenty-five" into the words "twenty" and "-five".
    words = [word("It", 1.0), word("was", 1.2), word("twenty", 1.5)]
    words += [word("-five", 1.9, 2.2), word("dollars.", 2.3, 2.8)]
    text = "It was twenty-five dollars."
    seg = Segment(id=0, start=1.0, end=2.8, text=text, words=words, speaker="S0")

    assert timed(clip_words(transcript(seg), 1.0, 3.0)) == [
        ("It", 0, 200),
        ("was", 200, 400),
        ("twenty-five", 500, 1200),
        ("dollars.", 1300, 1800),
    ]


def test_words_that_do_not_spell_their_text_show_one_by_one() -> None:
    words = [word("Howdy", 1.0), word(" ", 1.3), word("partner.", 1.5)]
    seg = Segment(
        id=0, start=1.0, end=2.0, text="Hello there.", words=words, speaker="S0"
    )

    assert timed(clip_words(transcript(seg), 1.0, 2.0)) == [
        ("Howdy", 0, 200),
        ("partner.", 500, 700),
    ]


def test_overrides_replace_the_text_of_words_with_their_start_and_end() -> None:
    words = [word("twenty", 1.5), word("-five", 1.9, 2.2), word("bucks", 2.3)]
    words.append(word("um,", 2.6))
    text = "twenty-five bucks um,"
    seg = Segment(id=0, start=1.5, end=2.8, text=text, words=words, speaker="S0")
    overrides = [word("-six", 1.9, 2.2), word("dollars", 2.3), word(" ", 2.6)]
    overrides.append(word("unmatched", 2.3, 2.6))

    assert timed(clip_words(transcript(seg), 1.0, 3.0, overrides)) == [
        ("twenty-six", 500, 1200),
        ("dollars", 1300, 1500),
    ]


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("Pizza.", "pizza"),
        ('"Wow!"', "wow"),
        ("don't", "don't"),
        ("twenty-five,", "twenty-five"),
        ("ÉCOLE", "école"),
        ("...", ""),
    ],
)
def test_keys_are_lowercase_without_the_punctuation_around(text: str, key: str) -> None:
    assert word_key(text) == key


def test_times_round_to_whole_milliseconds() -> None:
    assert [to_ms(seconds) for seconds in (10.36, 1.41, 0.1 + 0.2)] == [
        10360,
        1410,
        300,
    ]


def test_emphasis_marks_words_and_phrases_by_key() -> None:
    words = [cw(text, 0) for text in "Listen to your BODY! body your dog".split()]
    words[4] = CaptionWord("body", 0, 200, emphasis=True)

    marked = mark_emphasis(words, ["your body", "Dog.", " ", "cat"])

    assert [word.emphasis for word in marked] == [
        False,
        False,
        True,
        True,
        False,
        False,
        True,
    ]
    assert timed(marked) == timed(words)


def test_lines_break_after_punctuation() -> None:
    words = "So, I tried yoga. “Wow!” it was".split()

    lines = group_lines([cw(text, 250 * i) for i, text in enumerate(words)], 4)

    assert texts(lines) == [["So,"], ["I", "tried", "yoga."], ["“Wow!”"], ["it", "was"]]


@pytest.mark.parametrize(
    ("text", "breaks"),
    [
        ("so,", True),
        ("what?!", True),
        ('said."', True),
        ("(really?)", True),
        ("wait—", True),
        ("so…", True),
        ("3.5", False),
        ("(really)", False),
        ("don't", False),
    ],
)
def test_which_punctuation_ends_a_line(text: str, breaks: bool) -> None:
    assert line_break(cw(text, 0), cw("next", 250)) is breaks


def test_lines_break_at_pauses_longer_than_300_ms() -> None:
    words = [cw("a", 0, 200), cw("b", 500, 700), cw("c", 1001, 1100)]
    words.append(cw("d", 1150, 1200))

    assert texts(group_lines(words, 4)) == [["a", "b"], ["c", "d"]]


@pytest.mark.parametrize(("max_words", "sizes"), [(3, [3, 3, 1]), (4, [4, 3])])
def test_lines_hold_at_most_max_words(max_words: int, sizes: list[int]) -> None:
    words = [cw(f"w{i}", 250 * i) for i in range(7)]

    assert [len(line) for line in group_lines(words, max_words)] == sizes
    assert group_lines([], max_words) == []


def test_a_word_is_active_until_the_next_starts_unless_a_pause_comes() -> None:
    current = cw("a", 1000, 1200)

    assert active_end(current, cw("b", 1500)) == 1500
    assert active_end(current, cw("b", 1501)) == 1200
    assert active_end(current, cw("b", 1100)) == 1100
    assert active_end(current, None) == 1200
