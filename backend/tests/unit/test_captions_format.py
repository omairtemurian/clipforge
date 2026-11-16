"""Tests of the ASS formatting in pipeline/captions and caption_effects:
times, colors, escapes,
the text of one word and the Dialogue lines of caption lines."""

from pathlib import Path

import pytest
from clipforge.captions_templates import get_template, load_emoji_map
from clipforge.pipeline.caption_effects import bgr, escape, word_text
from clipforge.pipeline.caption_lines import CaptionWord, group_lines
from clipforge.pipeline.captions import ass_time, caption_events, captions_path

WORD_JOINER = "\u2060"


@pytest.mark.parametrize(
    ("ms", "text"),
    [
        (0, "0:00:00.00"),
        (1414, "0:00:01.41"),
        (1415, "0:00:01.42"),
        (2500, "0:00:02.50"),
        (61415, "0:01:01.42"),
        (3_599_995, "1:00:00.00"),
        (3_725_004, "1:02:05.00"),
    ],
)
def test_times_are_h_mm_ss_cc_rounded_half_up(ms: int, text: str) -> None:
    assert ass_time(ms) == text


def test_colors_are_blue_green_red() -> None:
    assert [bgr("#ffd23f"), bgr("#00E5FF"), bgr("#FF6B35")] == [
        "3FD2FF",
        "FFE500",
        "356BFF",
    ]


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("{\\b1}hi", "\\{\\" + WORD_JOINER + "b1\\}hi"),
        ("a\\Nb", "a\\" + WORD_JOINER + "Nb"),
        (" two\n lines\t ", "two lines"),
        ("plain", "plain"),
    ],
)
def test_text_shows_as_written_on_one_line(text: str, escaped: str) -> None:
    assert escape(text) == escaped


def test_the_emoji_of_a_keyword_follows_it_in_the_emoji_font() -> None:
    neon, karaoke = get_template("neon"), get_template("karaoke_bold")
    emoji = load_emoji_map()
    pizza = CaptionWord("Pizza!", 0, 100)
    emphasized = CaptionWord("pizza", 0, 100, emphasis=True)

    assert word_text(pizza, False, neon, emoji) == r"PIZZA! {\fnNoto Emoji}🍕{\fn}"
    assert word_text(emphasized, True, neon, emoji) == (
        r"{\c&HD62BFF&\fscx110\fscy110}PIZZA{\r} {\fnNoto Emoji}🍕{\fn}"
    )
    assert word_text(pizza, False, karaoke, emoji) == "PIZZA!"


def test_a_word_active_for_less_than_a_centisecond_gets_no_dialogue() -> None:
    words = [CaptionWord("a", 0, 4), CaptionWord("b", 4, 300)]

    events = caption_events(group_lines(words, 3), get_template("minimal"), {})

    assert events == [
        r"Dialogue: 0,0:00:00.00,0:00:00.30,Caption,,0,0,0,,a {\c&HFFFFFF&}b{\r}"
    ]


def test_captions_go_next_to_the_crop_plans(tmp_path: Path) -> None:
    assert captions_path(tmp_path, 3) == tmp_path / "captions_3.ass"
