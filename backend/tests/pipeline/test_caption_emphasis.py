"""Tests of AI emphasis words, emojis and speaker colors in captions
(SPEC-v2 3.4): the LLM's marks (recorded replies) become word marks, an
editor's mark beats the AI's, and the ASS file shows both and the colors of
the diarized speakers."""

import json
from pathlib import Path
from typing import Any

import pytest
from builders import SIX, make_clip
from caption_fakes import dialogues, write
from clipforge.models import CaptionMark, CaptionStyle, Transcript
from clipforge.pipeline.caption_emphasis import (
    CaptionEmphasisError,
    generate_marks,
    with_ai_marks,
)
from clipforge.pipeline.captions import write_captions
from clipforge.pipeline.step import TRANSCRIPT, write_json
from fakes import FakeLLMClient
from pydantic import ValidationError

# "Wait, my brother ate the pizza." are words 0-5 of the clip, starting at
# 10.0, 10.36, 10.54, 10.84, 11.14 and 11.7 s.
REPLY = json.dumps(
    {
        "marks": [
            {"index": 2, "emphasis": True, "emoji": "🔥"},
            {"index": 5, "emphasis": False, "emoji": "🍕"},
            {"index": 0},
            {"index": 40, "emphasis": True},
        ]
    }
)


@pytest.fixture
def work(tmp_path: Path) -> Path:
    write_json(
        tmp_path / TRANSCRIPT,
        Transcript(language="en", duration=60, segments=[SIX]),
    )
    return tmp_path


def two_speakers() -> Transcript:
    """The six words of SIX, the last three said by speaker S1."""
    words = [
        word.model_copy(update={"speaker": "S1"}) if index >= 3 else word
        for index, word in enumerate(SIX.words)
    ]
    return Transcript(
        language="en",
        duration=60,
        segments=[SIX.model_copy(update={"words": words})],
    )


def marked(ass: str) -> list[str]:
    """Return the Caption texts of ass, one per Dialogue line."""
    return [line.split(",,0,0,0,,")[1] for line in dialogues(ass)[1:]]


def test_the_llm_marks_numbered_words_and_gets_the_prompt(work: Path) -> None:
    llm = FakeLLMClient(REPLY)

    marks = generate_marks(llm, work, make_clip("minimal"))

    assert marks == [
        CaptionMark(start=10.54, emphasis=True, emoji="🔥", source="ai"),
        CaptionMark(start=11.7, emoji="🍕", source="ai"),
    ]
    system, user = llm.calls[0]
    assert '"marks"' in system and '"emphasis"' in system and "$schema" not in system
    assert user == (
        "The words of the clip:\n0: Wait,\n1: my\n2: brother\n3: ate\n4: the\n5: pizza."
    )


def test_a_reply_with_a_bad_emoji_is_sent_back_and_asked_again(work: Path) -> None:
    bad = json.dumps({"marks": [{"index": 1, "emoji": "fire"}]})
    llm = FakeLLMClient(bad, REPLY)

    marks = generate_marks(llm, work, make_clip("minimal"))

    assert len(marks) == 2
    assert "Your previous reply was not valid" in llm.calls[1][1]
    assert "emoji" in llm.calls[1][1]


def test_a_clip_gets_no_marks_if_the_llm_never_replies_validly(work: Path) -> None:
    llm = FakeLLMClient("not json", repeat_last=True)

    with pytest.raises(CaptionEmphasisError, match="clip 7 in 3 tries"):
        generate_marks(llm, work, make_clip("minimal"))

    assert len(llm.calls) == 3


def test_a_clip_without_words_asks_nothing(work: Path) -> None:
    llm = FakeLLMClient()

    assert generate_marks(llm, work, make_clip("minimal", start=40, end=41)) == []
    assert llm.calls == []


def test_ai_marks_show_in_the_captions(work: Path, tmp_path: Path) -> None:
    clip = make_clip("minimal", emphasis_words=[])
    style = with_ai_marks(
        clip.caption_style, generate_marks(FakeLLMClient(REPLY), work, clip)
    )

    ass = write(work, clip.model_copy(update={"caption_style": style}))

    assert marked(ass) == [
        r"{\c&HFFFFFF&}Wait,{\r}",
        r"{\c&HFFFFFF&}my{\r} {\c&H3FD2FF&\fscx110\fscy110}brother{\r} "
        r"{\fnNoto Emoji}🔥{\fn} ate",
        r"my {\c&HFFFFFF&\fscx110\fscy110}brother{\r} {\fnNoto Emoji}🔥{\fn} ate",
        r"my {\c&H3FD2FF&\fscx110\fscy110}brother{\r} {\fnNoto Emoji}🔥{\fn} "
        r"{\c&HFFFFFF&}ate{\r}",
        r"{\c&HFFFFFF&}the{\r}",
        r"{\c&HFFFFFF&}pizza.{\r} {\fnNoto Emoji}🍕{\fn}",
    ]


def test_the_editors_marks_beat_the_ais_and_survive_a_new_ai_pass(
    work: Path,
) -> None:
    edits = [
        CaptionMark(start=10.54, emphasis=False, emoji=""),
        CaptionMark(start=11.14, emphasis=True, emoji="⭐"),
    ]
    clip = make_clip("minimal", caption_style=CaptionStyle(word_marks=edits))
    ai = generate_marks(FakeLLMClient(REPLY), work, clip)

    style = with_ai_marks(clip.caption_style, ai)
    ass = write(work, clip.model_copy(update={"caption_style": style}))

    assert style.word_marks == [*edits, *ai]
    assert with_ai_marks(style, []).word_marks == edits
    # "brother" is an emphasis word of the clip: the editor turned it off and
    # removed the AI's emoji; the pizza keeps the AI's emoji.
    texts = marked(ass)
    assert texts[2] == r"my {\c&HFFFFFF&}brother{\r} ate"
    assert texts[4] == (r"{\c&HFFFFFF&\fscx110\fscy110}the{\r} {\fnNoto Emoji}⭐{\fn}")
    assert texts[5].endswith(r"{\fnNoto Emoji}🍕{\fn}")


def test_a_marked_emoji_shows_even_if_the_template_has_emoji_off(
    work: Path,
) -> None:
    style = CaptionStyle(word_marks=[CaptionMark(start=11.7, emoji="🍕")])
    clip = make_clip("minimal", caption_style=style)

    assert marked(write(work, clip))[5].endswith(r"{\fnNoto Emoji}🍕{\fn}")


def test_a_marked_color_beats_emphasis_and_speaker_colors_but_not_the_spoken_word(
    tmp_path: Path,
) -> None:
    write_json(tmp_path / TRANSCRIPT, two_speakers())
    marks = [
        CaptionMark(start=10.54, color="#00AAFF"),
        CaptionMark(start=10.84, color="#123456"),
    ]
    style = CaptionStyle(word_marks=marks, speaker_colors={"S1": "#FF00FF"})
    clip = make_clip("minimal", emphasis_words=["brother"], caption_style=style)

    texts = marked(
        write_captions(tmp_path, clip, (540, 960), 30).read_text(encoding="utf-8")
    )

    # "brother" (an emphasis word) and "ate" (speaker S1) show their marked
    # colors, and the highlight color while they are spoken.
    assert texts[1] == (
        r"{\c&HFFFFFF&}my{\r} {\c&HFFAA00&\fscx110\fscy110}brother{\r} "
        r"{\c&H563412&}ate{\r}"
    )
    assert texts[2].startswith(r"my {\c&HFFFFFF&\fscx110\fscy110}brother{\r}")


def test_a_mark_finds_its_word_by_source_time_after_cuts(work: Path) -> None:
    style = CaptionStyle(word_marks=[CaptionMark(start=11.7, emphasis=True)])
    cut = make_clip("minimal", cut_ranges=[(10.3, 10.52)], caption_style=style)

    texts = marked(write(work, cut))

    assert texts[-1] == r"{\c&HFFFFFF&\fscx110\fscy110}pizza.{\r}"
    assert not any("my" in text for text in texts)


def test_speaker_colors_color_each_speakers_words(tmp_path: Path) -> None:
    write_json(tmp_path / TRANSCRIPT, two_speakers())
    style = CaptionStyle(speaker_colors={"S0": "#00FF00", "S1": "#FF00FF"})

    def captions(**changes: Any) -> list[str]:
        clip = make_clip("minimal", caption_style=style, **changes)
        return marked(
            write_captions(tmp_path, clip, (540, 960), 30).read_text(encoding="utf-8")
        )

    assert captions(emphasis_words=[]) == [
        r"{\c&HFFFFFF&}Wait,{\r}",
        r"{\c&HFFFFFF&}my{\r} {\c&H00FF00&}brother{\r} {\c&HFF00FF&}ate{\r}",
        r"{\c&H00FF00&}my{\r} {\c&HFFFFFF&}brother{\r} {\c&HFF00FF&}ate{\r}",
        r"{\c&H00FF00&}my{\r} {\c&H00FF00&}brother{\r} {\c&HFFFFFF&}ate{\r}",
        r"{\c&HFFFFFF&}the{\r}",
        r"{\c&HFFFFFF&}pizza.{\r}",
    ]
    # An emphasis word keeps the emphasis color, not its speaker's.
    assert captions(emphasis_words=["ate"])[1].endswith(
        r"{\c&H3FD2FF&\fscx110\fscy110}ate{\r}"
    )


def test_a_speaker_without_a_color_keeps_the_template_colors(
    tmp_path: Path,
) -> None:
    write_json(tmp_path / TRANSCRIPT, two_speakers())
    style = CaptionStyle(speaker_colors={"S1": "#FF00FF"})
    clip = make_clip("minimal", emphasis_words=[], caption_style=style)

    ass = write_captions(tmp_path, clip, (540, 960), 30).read_text(encoding="utf-8")

    assert marked(ass)[1] == (r"{\c&HFFFFFF&}my{\r} brother {\c&HFF00FF&}ate{\r}")


def test_a_mark_needs_a_single_emoji() -> None:
    with pytest.raises(ValidationError):
        CaptionMark(start=1, emoji="ab")
    with pytest.raises(ValidationError):
        CaptionStyle(speaker_colors={"S0": "green"})
    assert CaptionMark(start=1, emoji="").emoji == ""
