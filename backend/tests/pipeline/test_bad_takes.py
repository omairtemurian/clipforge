"""Tests of bad takes (SPEC-v2 3.5): the clip's words numbered for the
LLM (mocked), its picks checked and sent back with their errors, and the
cut each usable take makes."""

import json

import pytest
from builders import cleanup_item, make_clip, said
from clipforge.models import Transcript
from clipforge.pipeline.bad_takes import (
    BadTakesError,
    find_bad_takes,
    take_words,
    user_prompt,
)
from clipforge.pipeline.step import TRANSCRIPT
from fakes import FIXTURES, FakeLLMClient

FIXTURE = Transcript.model_validate_json((FIXTURES / TRANSCRIPT).read_bytes())
# "So the best way, the best way to start is coffee."
RETAKE = said(
    ("So", 1.0, 1.2),
    (" the", 1.3, 1.4),
    (" best", 1.45, 1.7),
    (" way,", 1.75, 2.0),
    (" the", 2.3, 2.4),
    (" best", 2.45, 2.7),
    (" way", 2.75, 2.9),
    (" to", 2.95, 3.05),
    (" start", 3.1, 3.4),
    (" is", 3.45, 3.55),
    (" coffee.", 3.6, 4.0),
)
RETAKE_CLIP = make_clip("karaoke_bold", start=1.0, end=4.0)


def takes(*picks: tuple[int, int]) -> str:
    """Return an LLM reply with the bad takes picks (first, last)."""
    return json.dumps({"takes": [{"first": f, "last": la} for f, la in picks]})


def test_the_llm_sees_numbered_words_with_section_breaks() -> None:
    clip = make_clip("karaoke_bold", segments=[(16.9, 19.7), (0.5, 2.9)])

    prompt = user_prompt(take_words(FIXTURE, clip))

    assert prompt.splitlines()[:3] == ["The words of the clip:", "0: Then", "1: I"]
    assert "7: fridges.\n---\n8: Hi\n9: everyone." in prompt


def test_words_the_clip_already_cuts_are_not_numbered() -> None:
    clip = RETAKE_CLIP.model_copy(update={"cut_ranges": [(1.3, 2.3)]})

    words = [word.text for word in take_words(RETAKE, clip)]

    assert words == ["So", "the", "best", "way", "to", "start", "is", "coffee."]


def test_a_repeated_take_is_cut_up_to_the_next_word() -> None:
    llm = FakeLLMClient(takes((1, 3)))
    words = take_words(RETAKE, RETAKE_CLIP)

    found = find_bad_takes(llm, words, 7)

    assert found == [cleanup_item(1.3, 2.3, "bad_take", "the best way,")]
    [(system, user)] = llm.calls
    assert '"takes"' in system and "repeated" in system
    assert "1: the\n2: best\n3: way," in user


def test_a_take_at_a_sections_end_is_cut_to_its_last_word() -> None:
    clip = make_clip("karaoke_bold", segments=[(1.0, 2.1), (2.3, 4.0)])
    words = take_words(RETAKE, clip)

    found = find_bad_takes(FakeLLMClient(takes((1, 3))), words, 7)

    assert found == [cleanup_item(1.3, 2.0, "bad_take", "the best way,")]


def test_invalid_replies_are_sent_back_with_their_errors() -> None:
    llm = FakeLLMClient("not json", takes((5, 40)), takes((1, 3)))
    words = take_words(RETAKE, RETAKE_CLIP)

    found = find_bad_takes(llm, words, 7)

    assert [i.text for i in found] == ["the best way,"]
    assert len(llm.calls) == 3
    assert "takes.0: words 5-40 do not exist" in llm.calls[2][1]


def test_after_the_last_try_only_usable_takes_are_kept() -> None:
    words = take_words(RETAKE, RETAKE_CLIP)
    clip = make_clip("karaoke_bold", segments=[(1.0, 2.1), (2.3, 4.0)])
    llm = FakeLLMClient(takes((1, 3), (2, 4), (3, 5)), repeat_last=True)

    found = find_bad_takes(llm, words, 7)
    across = find_bad_takes(llm, take_words(RETAKE, clip), 7)

    assert [(i.start, i.end) for i in found] == [(1.3, 2.3)]
    assert len(llm.calls) == 6
    assert "takes.1: overlaps another take" in llm.calls[1][1]
    assert "takes.2: runs across a section break" in llm.calls[4][1]
    assert [(i.start, i.end) for i in across] == [(1.3, 2.0)]


def test_takes_that_leave_no_word_are_not_kept() -> None:
    words = take_words(RETAKE, RETAKE_CLIP)

    found = find_bad_takes(FakeLLMClient(takes((0, 10)), repeat_last=True), words, 7)

    assert found == []


def test_no_valid_reply_is_an_error_and_no_words_ask_nothing() -> None:
    words = take_words(RETAKE, RETAKE_CLIP)
    with pytest.raises(BadTakesError, match="3 tries"):
        find_bad_takes(FakeLLMClient("{}", repeat_last=True), words, 7)
    llm = FakeLLMClient()

    assert find_bad_takes(llm, [], 7) == []
    assert llm.calls == []
