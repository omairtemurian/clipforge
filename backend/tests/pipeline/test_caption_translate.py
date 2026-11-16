"""Tests of caption translation (SPEC-v2 3.4): the LLM (recorded replies)
translates a clip's numbered caption cues, each cue keeps the time of the
words it translates, invalid replies are sent back, and render shows the
translated words in each cue's time, after the clip's cuts."""

import json
from pathlib import Path

import pytest
from builders import SIX, make_clip
from caption_fakes import dialogues
from clipforge.models import (
    CaptionCue,
    CaptionStyle,
    CaptionTranslation,
    Transcript,
)
from clipforge.pipeline.caption_cues import spread_cue, translated_words
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.caption_translate import (
    CaptionTranslateError,
    translate_captions,
)
from clipforge.pipeline.captions import write_captions
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.polish import rendered_words
from clipforge.pipeline.step import TRANSCRIPT, write_json
from fakes import FakeLLMClient

# The cues of SIX in clip 10-12.5 s: a pause of 450 ms ends the first.
PROMPT = (
    "Translate into: Persian (fa)\n"
    "The clip is in: English (en)\n\n"
    "The caption cues of the clip:\n"
    "0: Wait, my brother ate the\n"
    "1: pizza."
)
FIRST, SECOND = "صبر کن، برادرم خورد", "پیتزا را!"
REPLY = json.dumps(
    {"cues": [{"index": 1, "text": SECOND}, {"index": 0, "text": FIRST}]}
)
TRANSLATION = CaptionTranslation(
    language="fa",
    cues=[
        CaptionCue(start=10.0, end=11.25, text=FIRST, speaker="S0"),
        CaptionCue(start=11.7, end=12.2, text=SECOND, speaker="S0"),
    ],
)


@pytest.fixture
def work(tmp_path: Path) -> Path:
    write_json(
        tmp_path / TRANSCRIPT,
        Transcript(language="en", duration=60, segments=[SIX]),
    )
    return tmp_path


def reply(*cues: tuple[int, str]) -> str:
    return json.dumps({"cues": [{"index": i, "text": text} for i, text in cues]})


def test_the_llm_translates_numbered_cues_that_keep_their_times(work: Path) -> None:
    llm = FakeLLMClient(REPLY)

    translation = translate_captions(llm, work, make_clip("minimal"), "fa")

    assert translation == TRANSLATION
    system, user = llm.calls[0]
    assert user == PROMPT
    assert '"cues"' in system and '"index"' in system and "$schema" not in system


def test_the_cues_use_the_editors_caption_text(work: Path) -> None:
    llm = FakeLLMClient(reply((0, "Espera, mi hermano"), (1, "la pizza.")))
    fixed = SIX.words[2].model_copy(update={"text": "sister"})
    clip = make_clip("minimal", caption_overrides=[fixed])

    translation = translate_captions(llm, work, clip, "es")

    assert llm.calls[0][1].endswith("0: Wait, my sister ate the\n1: pizza.")
    assert [(cue.start, cue.end) for cue in translation.cues] == [
        (10.0, 11.25),
        (11.7, 12.2),
    ]


@pytest.mark.parametrize(
    ("bad", "error"),
    [
        (reply((0, FIRST)), "- cues: no translation of cue 1"),
        (
            reply((0, FIRST), (0, FIRST), (1, SECOND)),
            "- cues: cue 0 is translated twice",
        ),
        (reply((0, FIRST), (1, SECOND), (2, "x")), "- cues: there is no cue 2"),
        (reply((0, FIRST), (1, "   ")), "- cues.1.text: String should match pattern"),
        ("not json", "- reply: Invalid JSON"),
    ],
)
def test_an_invalid_reply_is_sent_back_with_its_errors(
    work: Path, bad: str, error: str
) -> None:
    llm = FakeLLMClient(bad, REPLY)

    translation = translate_captions(llm, work, make_clip("minimal"), "fa")

    assert translation == TRANSLATION
    again = llm.calls[1][1]
    assert again.startswith(PROMPT + "\n\nYour previous reply was not valid:\n")
    assert error in again


def test_no_valid_reply_raises(work: Path) -> None:
    llm = FakeLLMClient(reply((0, FIRST)), repeat_last=True)

    with pytest.raises(CaptionTranslateError, match="no valid translation of clip 7"):
        translate_captions(llm, work, make_clip("minimal"), "fa")

    assert len(llm.calls) == MAX_RETRIES + 1


def test_a_clip_without_words_asks_nothing(work: Path) -> None:
    llm = FakeLLMClient()
    clip = make_clip("minimal", start=30.0, end=40.0)

    translation = translate_captions(llm, work, clip, "he")

    assert translation == CaptionTranslation(language="he", cues=[])
    assert llm.calls == []


def test_a_cue_shares_its_time_out_by_the_length_of_its_words() -> None:
    cue = CaptionCue(start=10.0, end=11.25, text="aaa  bb\nc")

    assert spread_cue(cue) == [
        ("aaa", 10000, 10556),
        ("bb", 10556, 10972),
        ("c", 10972, 11250),
    ]


def test_translated_words_start_in_the_clip_and_end_at_its_end() -> None:
    words = translated_words(TRANSLATION, 10.5, 12.0)

    assert words == [
        CaptionWord("برادرم", 0, 438, speaker="S0"),
        CaptionWord("خورد", 438, 750, speaker="S0"),
        CaptionWord("پیتزا", 1200, 1500, speaker="S0"),
    ]


def test_render_shows_the_translation_each_cue_in_its_time(work: Path) -> None:
    clip = make_clip("minimal", caption_style=CaptionStyle(translation=TRANSLATION))

    ass = write_captions(work, clip, (1080, 1920), 30).read_text(encoding="utf-8")

    assert "Style: Caption,Vazirmatn Bold," in ass
    times = [line.split(",")[1:3] for line in dialogues(ass)[1:]]
    assert len(times) == 6
    assert times[0][0] == "0:00:00.00" and times[3][1] == "0:00:01.25"
    assert times[4][0] == "0:00:01.70" and times[5][1] == "0:00:02.20"
    assert "پیتزا" in dialogues(ass)[-1] and "را!" in dialogues(ass)[-1]


def test_cuts_retime_the_translated_words(work: Path) -> None:
    style = CaptionStyle(translation=TRANSLATION)
    clip = make_clip(
        "minimal",
        caption_style=style,
        cut_ranges=[(11.3, 11.7)],
    )

    words = rendered_words(
        Transcript(language="en", duration=60, segments=[]), clip, 100
    )

    assert [(word.text, word.start, word.end) for word in words[-2:]] == [
        ("پیتزا", 1300, 1600),
        ("را!", 1600, 1800),
    ]
