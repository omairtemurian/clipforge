"""Tests of Pro Edit's kinetic captions (SPEC-v3 3.3): the styles, the loud
words and the ASS tags of each style, and that the existing templates draw
as before."""

import hashlib
import re
import statistics
from pathlib import Path
from typing import get_args

import numpy as np
import pytest
from clipforge.captions_templates import load_emoji_map, load_templates
from clipforge.pipeline.caption_effects import word_text
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.captions import build_ass
from clipforge.pipeline.loudness import Envelope
from clipforge.proedit.captions import kinetic, loud, styles
from clipforge.proedit.captions.kinetic import KineticFx, kinetic_ass
from clipforge.proedit.edl_params import CaptionStyleParams

FRAME = (540, 960)
WORDS = [
    CaptionWord("Wait", 0, 360),
    CaptionWord("my", 360, 540),
    CaptionWord("brother", 540, 840),
    CaptionWord("laughed", 840, 1140),
]
# The digest of the ASS of every existing template (fixed words, emphasis,
# speaker color, mark emoji and hook) before kinetic captions existed.
EXISTING_TEMPLATES_DIGEST = (
    "a6331bda1abd36ce0712cd4eec93bc43883f63c54e1bc5383b21d0bc52b5c8c8"
)


def params(**fields: object) -> CaptionStyleParams:
    """Params of the "pop" style with fields changed."""
    return CaptionStyleParams.model_validate({"style": "pop", **fields})


def dialogue_texts(ass: str) -> list[str]:
    """The text of each Caption Dialogue line of ass."""
    return [
        line.split(",,0,0,0,,", 1)[1]
        for line in ass.splitlines()
        if line.startswith("Dialogue:")
    ]


def blocks(text: str) -> list[str]:
    """The override blocks of a Dialogue text."""
    return re.findall(r"\{[^}]*\}", text)


def moving(text: str) -> int:
    """How many words of a Dialogue text carry a \\t animation."""
    return sum("\\t(" in block for block in blocks(text) if "\\fn" not in block)


def fx(**fields: object) -> KineticFx:
    """A pop fx without glow, emphasis at 120 %, with fields changed."""
    base: dict[str, object] = {
        "motion": "pop",
        "glow": False,
        "emphasis_percent": 120,
        "shake_on_loud": False,
    }
    return KineticFx(**{**base, **fields})  # type: ignore[arg-type]


def test_there_is_a_style_file_for_each_style_param() -> None:
    names = set(get_args(CaptionStyleParams.model_fields["style"].annotation))

    assert set(styles.load_styles()) == names


def test_styles_leave_the_motion_to_kinetic_and_are_not_caption_templates() -> None:
    for style in styles.load_styles().values():
        assert style.caption.animation == "none"
    assert styles.get_style("single_word").caption.max_words_per_line == 1


def test_an_unknown_style_lists_the_known_ones() -> None:
    with pytest.raises(ValueError, match="unknown kinetic caption style 'x'.*neon"):
        styles.get_style("x")


def test_a_style_file_with_an_unbundled_font_or_a_wrong_field_is_refused(
    tmp_path: Path,
) -> None:
    text = (styles.STYLES_DIR / "pop.yaml").read_text(encoding="utf-8")
    bad_font = tmp_path / "font.yaml"
    bad_font.write_text(text.replace("Montserrat ExtraBold", "Nope"), encoding="utf-8")
    bad_field = tmp_path / "field.yaml"
    bad_field.write_text(text + "extra: 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="font 'Nope'"):
        styles.load_style(bad_font)
    with pytest.raises(ValueError, match="not a valid kinetic style"):
        styles.load_style(bad_field)


def tone(seconds: float, amplitude: float) -> np.ndarray:
    """A 16 kHz sine of seconds at amplitude."""
    t = np.arange(round(seconds * 16000)) / 16000
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_a_word_twice_as_loud_as_the_others_is_loud_by_its_rms() -> None:
    samples = np.concatenate(
        [tone(0.36, 0.1), tone(0.18, 0.1), tone(0.30, 0.4), tone(0.30, 0.1)]
    )

    found = loud.loud_words(WORDS, loud.envelope_of(samples))

    assert found == frozenset({540})


def test_the_threshold_is_in_db_above_the_median_word() -> None:
    samples = np.concatenate(
        [tone(0.36, 0.1), tone(0.18, 0.1), tone(0.30, 0.4), tone(0.30, 0.1)]
    )
    envelope = loud.envelope_of(samples)
    levels = loud.word_levels(WORDS, envelope)

    over = levels[540] - statistics.median(levels.values())
    assert over == pytest.approx(11.3, abs=0.3)
    assert loud.loud_words(WORDS, envelope, over_db=over - 0.5) == {540}
    assert loud.loud_words(WORDS, envelope, over_db=over + 0.5) == frozenset()


def test_even_speech_has_no_loud_word_and_no_audio_none() -> None:
    envelope = loud.envelope_of(tone(1.2, 0.2))

    assert loud.loud_words(WORDS, envelope) == frozenset()
    assert loud.loud_words(WORDS, Envelope(0.0, np.zeros(0, np.float32))) == frozenset()
    assert loud.word_levels(WORDS, Envelope(0.0, np.zeros(0, np.float32))) == {}


def test_only_the_active_word_moves() -> None:
    texts = dialogue_texts(kinetic_ass(WORDS, params(), FRAME, emoji_map={}))

    assert len(texts) == 4
    assert [moving(text) for text in texts] == [1, 1, 1, 1]
    for index, text in enumerate(texts):
        assert moving(text) == 1
        assert len(text.split("{")[0].split()) == index % 3


def test_pop_overshoots_then_settles_and_bounce_dips_under_its_size() -> None:
    word = CaptionWord("Pizza", 0, 500)
    template = styles.get_style("pop").caption

    popped = kinetic.kinetic_word_text(word, True, template, {}, fx())
    bounced = kinetic.kinetic_word_text(word, True, template, {}, fx(motion="bounce"))

    assert popped.startswith(
        "{\\c&H00E6FF&\\fscx70\\fscy70\\t(0,90,\\fscx108\\fscy108)"
        "\\t(90,180,\\fscx100\\fscy100)}PIZZA{\\r}"
    )
    assert bounced.count("\\t(") == 3
    assert "\\fscx115" in bounced and "\\fscx96" in bounced
    assert bounced.index("\\fscx115") < bounced.index("\\fscx96")


def test_a_word_that_is_not_active_has_no_animation_tags() -> None:
    template = styles.get_style("neon").caption
    word = CaptionWord("Pizza", 0, 500)

    text = kinetic.kinetic_word_text(
        word,
        False,
        template,
        {},
        fx(glow=True, shake_on_loud=True, loud=frozenset({0})),
    )

    assert text == "PIZZA"
    for tag in ("\\t(", "\\frz", "\\blur", "\\bord"):
        assert tag not in text


def test_emphasis_words_are_scaled_by_emphasis_scale_active_or_not() -> None:
    template = styles.get_style("pop").caption
    word = CaptionWord("brother", 0, 500, emphasis=True)

    idle = kinetic.kinetic_word_text(
        word, False, template, {}, fx(emphasis_percent=140)
    )
    active = kinetic.kinetic_word_text(
        word, True, template, {}, fx(emphasis_percent=140)
    )

    assert idle == "{\\c&H14FF39&\\fscx140\\fscy140}BROTHER{\\r}"
    assert "\\fscx140\\fscy140)" in active
    assert word_text(word, False, template, {}).count("\\fscx110") == 1


def test_emphasis_scale_comes_from_the_params() -> None:
    ass = kinetic_ass(
        WORDS,
        params(emphasis_scale=1.5),
        FRAME,
        emphasis_words=["brother"],
        emoji_map={},
    )

    assert "\\fscx150\\fscy150}BROTHER" in dialogue_texts(ass)[0]
    assert "\\fscx110" not in ass


def test_a_loud_active_word_shakes_only_if_shake_on_loud_is_on() -> None:
    template = styles.get_style("pop").caption
    word = CaptionWord("no", 540, 840)
    calm = CaptionWord("no", 0, 360)
    on = fx(shake_on_loud=True, loud=frozenset({540}))

    assert "\\frz4" in kinetic.kinetic_word_text(word, True, template, {}, on)
    assert "\\frz" not in kinetic.kinetic_word_text(calm, True, template, {}, on)
    assert "\\frz" not in kinetic.kinetic_word_text(
        word, True, template, {}, fx(loud=frozenset({540}))
    )
    assert "\\frz" not in kinetic.kinetic_word_text(word, False, template, {}, on)


def test_the_ass_shakes_the_loud_word_found_by_rms() -> None:
    samples = np.concatenate(
        [tone(0.36, 0.1), tone(0.18, 0.1), tone(0.30, 0.4), tone(0.30, 0.1)]
    )
    found = loud.loud_words(WORDS, loud.envelope_of(samples))

    ass = kinetic_ass(
        WORDS, params(shake_on_loud=True), FRAME, loud=found, emoji_map={}
    )

    shaking = [index for index, t in enumerate(dialogue_texts(ass)) if "\\frz" in t]
    assert shaking == [2]


def test_neon_glows_the_active_word_in_its_highlight_color() -> None:
    template = styles.get_style("neon").caption
    word = CaptionWord("Pizza", 0, 500)

    text = kinetic.kinetic_word_text(word, True, template, {}, fx(glow=True))

    assert text.startswith("{\\c&HFFFFFF&\\3c&HD62BFF&\\bord9\\blur4\\fscx70")
    plain = kinetic.kinetic_word_text(word, True, template, {}, fx())
    assert "\\blur" not in plain and "\\bord" not in plain


def test_single_word_shows_one_word_a_page() -> None:
    ass = kinetic_ass(
        WORDS, CaptionStyleParams(style="single_word"), FRAME, emoji_map={}
    )

    texts = [re.sub(r"\{[^}]*\}", "", text) for text in dialogue_texts(ass)]
    assert texts == ["WAIT", "MY", "BROTHER", "LAUGHED"]


def test_emoji_pops_for_the_active_word_and_waits_for_upcoming_ones() -> None:
    emoji_map = {"wait": "✋", "brother": "👦"}
    ass = kinetic_ass(WORDS, params(emoji=True), FRAME, emoji_map=emoji_map)

    first, second, third = dialogue_texts(ass)[:3]
    pop = "{\\fnNoto Emoji\\fscx30\\fscy30\\t(0,90,\\fscx130\\fscy130)"
    assert pop + "\\t(90,180,\\fscx100\\fscy100)}✋" in first
    assert "{\\fnNoto Emoji\\alpha&HFF&}👦" in first
    assert "{\\fnNoto Emoji}✋" in second
    assert "{\\fnNoto Emoji\\alpha&HFF&}👦" in second
    assert pop + "\\t(90,180,\\fscx100\\fscy100)}👦" in third
    assert "{\\fnNoto Emoji}✋" in third


def test_emoji_off_draws_no_keyword_emoji_but_keeps_a_marked_one() -> None:
    marked = [CaptionWord("laughed", 0, 500, emoji="🔥")]
    keyword = [CaptionWord("laughed", 0, 500)]
    emoji_map = {"laughed": "😂"}

    assert "😂" not in kinetic_ass(keyword, params(), FRAME, emoji_map=emoji_map)
    assert "🔥" in kinetic_ass(marked, params(), FRAME, emoji_map=emoji_map)


def test_each_style_writes_a_valid_ass_with_its_font_and_position() -> None:
    for name, style in styles.load_styles().items():
        ass = kinetic_ass(
            WORDS,
            params(style=name),
            FRAME,
            emoji_map={},
        )

        assert f"Style: Caption,{style.caption.font}," in ass
        assert f"PlayResX: {FRAME[0]}" in ass
        assert len(dialogue_texts(ass)) == len(WORDS)


def test_existing_templates_draw_the_same_ass_as_before() -> None:
    words = [
        CaptionWord("Wait,", 0, 360),
        CaptionWord("my", 360, 540),
        CaptionWord("brother", 540, 840, speaker="A"),
        CaptionWord("laugh", 840, 1140),
        CaptionWord("pizza.", 1700, 2200, emoji="🍕"),
    ]
    digest = hashlib.sha256()
    for name, template in load_templates().items():
        digest.update(name.encode())
        ass = build_ass(
            words,
            template,
            FRAME,
            emphasis_words=["brother"],
            speaker_colors={"A": "#FF0000"},
            hook_text="Hi there",
            emoji_map=load_emoji_map(),
        )
        digest.update(ass.encode())
        assert ass == build_ass(
            words,
            template,
            FRAME,
            emphasis_words=["brother"],
            speaker_colors={"A": "#FF0000"},
            hook_text="Hi there",
            emoji_map=load_emoji_map(),
            word_writer=word_text,
        )

    assert digest.hexdigest() == EXISTING_TEMPLATES_DIGEST
