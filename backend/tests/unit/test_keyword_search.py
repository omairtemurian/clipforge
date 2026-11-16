"""Unit tests for the keyword search of curate (SPEC-v2 3.2): matching,
window goals, window growth and the search_terms setting."""

import pytest
from builders import segment, source_meta
from clipforge.config import Settings
from clipforge.models import LengthPreset, ProcessingSettings
from clipforge.pipeline.keyword_search import (
    bare,
    find_matches,
    grow,
    keyword_candidates,
    keyword_goal,
    normalize,
)
from pydantic import ValidationError

CFG = Settings(clip_min_s=20, clip_max_s=75)
SEGMENTS = [
    segment(0, "Café prices, café PRICES!", [0.0, 1.0, 2.0, 3.0], 4.0),
    segment(1, "The price - is right.", [10.0, 11.0, 12.0, 13.0, 14.0], 15.0),
    segment(2, "Is right here.", [20.0, 21.0, 22.0], 23.0),
]


def test_normalize_keeps_lowercase_letters_and_digits() -> None:
    assert normalize("Don't-Stop 2day!") == "dontstop2day"
    assert normalize("Ärger") == normalize("ärger") == "ärger"
    assert normalize(" - ") == ""


def test_bare_strips_the_punctuation_around_a_word() -> None:
    assert [bare(w) for w in (" Hello,", "'quoted'", "don't.", "...")] == [
        "Hello",
        "quoted",
        "don't",
        "",
    ]


def test_find_matches_ignores_case_and_punctuation() -> None:
    matches = find_matches(SEGMENTS, ["CAFÉ prices"])
    assert [(m.start, m.end, m.words) for m in matches] == [
        (0.0, 2.0, ("Café", "prices")),
        (2.0, 4.0, ("café", "PRICES")),
    ]


def test_find_matches_skips_punctuation_words_and_crosses_segments() -> None:
    matches = find_matches(SEGMENTS, ["price is", "right is right"])
    assert [(m.term, m.start, m.end) for m in matches] == [
        ("price is", 11.0, 14.0),
        ("right is right", 14.0, 22.0),
    ]
    assert (matches[1].first_segment, matches[1].last_segment) == (1, 2)


def test_find_matches_is_whole_words_and_sorted_by_start() -> None:
    matches = find_matches(SEGMENTS, ["here", "price", "is", "!!"])
    assert [(m.term, m.start) for m in matches] == [
        ("price", 11.0),
        ("is", 13.0),
        ("is", 20.0),
        ("here", 22.0),
    ]


@pytest.mark.parametrize(
    ("presets", "custom", "goal"),
    [
        (["auto"], None, (20.0, 74.7)),
        (["lt30"], None, (20.0, 29.7)),
        (["0_60", "60_90"], None, (20.0, 59.7)),
        (["30_60"], None, (30.0, 59.7)),
        (["custom"], (2.0, 4.0), (2.0, 3.7)),
        (["custom"], (10.0, 10.1), (10.0, 10.0)),
    ],
)
def test_keyword_goal_is_the_first_preset_with_room_for_the_tail(
    presets: list[LengthPreset],
    custom: tuple[float, float] | None,
    goal: tuple[float, float],
) -> None:
    low, high = custom or (None, None)
    processing = ProcessingSettings(
        length_presets=presets, custom_length_min_s=low, custom_length_max_s=high
    )
    assert keyword_goal(processing, CFG) == pytest.approx(goal)


def test_grow_adds_the_shorter_side_and_never_passes_the_floor() -> None:
    units = [(0.0, 1.0), (2.0, 3.0), (4.0, 5.0), (6.0, 9.0), (10.0, 11.0)]
    assert grow(units, 2, 2, 0, (4.0, 10.0)) == (0.0, 5.0)
    assert grow(units, 2, 2, 2, (4.0, 10.0)) == (4.0, 9.0)
    assert grow(units, 2, 2, 2, (0.5, 7.0)) == (4.0, 5.0)


def test_grow_stops_at_the_longest_or_the_last_unit() -> None:
    units = [(0.0, 1.0), (2.0, 3.0), (4.0, 5.0), (6.0, 9.0), (10.0, 11.0)]
    assert grow(units, 2, 2, 0, (8.0, 8.5)) == (0.0, 5.0)
    assert grow(units, 2, 2, 0, (20.0, 30.0)) == (0.0, 11.0)


def test_a_long_sentence_is_cut_by_words() -> None:
    long = segment(0, "a b c d e f g h i j", [float(t) for t in range(10)], 10.0)
    [found] = keyword_candidates([long], ["e f"], source_meta(), (3.0, 4.0))
    # On a tie the word after is added before the word before.
    assert (found.start, found.end) == (4.0, 7.0)


def test_windows_do_not_overlap() -> None:
    [first, second] = keyword_candidates(
        SEGMENTS, ["right"], source_meta(), (5.0, 30.0)
    )
    assert (first.start, first.end) == (10.0, 15.0)
    assert (second.start, second.end) == (20.0, 23.0)


def test_search_terms_are_tidied() -> None:
    processing = ProcessingSettings(
        search_terms=["  smart   fridge ", "Smart fridge", "", " ", "car"]
    )
    assert processing.search_terms == ["smart fridge", "car"]


@pytest.mark.parametrize("terms", [[], ["  "]])
def test_a_keyword_search_needs_a_search_term(terms: list[str]) -> None:
    with pytest.raises(ValidationError, match="at least one search term"):
        ProcessingSettings(clipping="keyword_search", search_terms=terms)


def test_search_terms_are_limited() -> None:
    with pytest.raises(ValidationError):
        ProcessingSettings(search_terms=[f"t{i}" for i in range(21)])
    with pytest.raises(ValidationError):
        ProcessingSettings(search_terms=["x" * 101])
