"""The SPEC-v2 3.4 caption templates: at least ten original templates with
the full style schema (position, size, font, colors, stroke, shadow, box,
uppercase, lines, words per line, animation), each writing its captions of
the six-word fixture and drawing a preview PNG; caption pages and clip
caption styles that set the new fields."""

from pathlib import Path

import numpy as np
import pytest
from builders import make_clip
from caption_fakes import caption_dialogues, dialogues, write
from clipforge.caption_previews import FRAME, ensure_preview, styled_preview
from clipforge.captions_templates import (
    CaptionTemplate,
    get_template,
    load_templates,
    style_problems,
)
from clipforge.models import CaptionStyle
from clipforge.pipeline.caption_lines import CaptionWord, group_pages
from frames import png_pixels

TEMPLATES = load_templates()
V1_TEMPLATES = {"karaoke_bold", "minimal", "boxed", "neon", "comic", "clean_subtitle"}
# What the spec asks a template to set -> the template's fields for it.
SCHEMA = {
    "position": ["position"],
    "size": ["size"],
    "font": ["font"],
    "colors": ["primary_color", "highlight_color", "emphasis_color"],
    "stroke": ["outline", "outline_color"],
    "shadow": ["shadow"],
    "box": ["box"],
    "uppercase": ["uppercase"],
    "lines": ["max_lines"],
    "words per line": ["max_words_per_line"],
    "animation": ["animation"],
}
POP = r"\fscx75\fscy75\t(0,120,\fscx100\fscy100)"
POP_EMPHASIS = r"\fscx75\fscy75\t(0,120,\fscx110\fscy110)"
BOUNCE = r"\fscx85\fscy85\t(0,90,\fscx105\fscy105)\t(90,180,\fscx100\fscy100)"
BOUNCE_EMPHASIS = r"\fscx85\fscy85\t(0,90,\fscx115\fscy115)\t(90,180,\fscx110\fscy110)"
FADE = r"{\fad(150,0)}"
HIDE = r"\alpha&HFF&"
# Each v2 template's hook, then the text of each word's Dialogue of
# "Wait, my brother ate the pizza." ("brother" is the emphasis word, a pause
# follows "the"; the v1 templates are in tests/unit/test_captions).
EXPECTED = {
    "pop_punch": [
        "HE ATE IT ALL",
        rf"{{\c&H00FFC6&{POP}}}WAIT,{{\r}}",
        rf"{{\c&H00FFC6&{POP}}}MY{{\r}} {{\c&H7F3DFF&\fscx110\fscy110}}BROTHER{{\r}}",
        rf"MY {{\c&H00FFC6&{POP_EMPHASIS}}}BROTHER{{\r}}",
        rf"{{\c&H00FFC6&{POP}}}ATE{{\r}} THE",
        rf"ATE {{\c&H00FFC6&{POP}}}THE{{\r}}",
        rf"{{\c&H00FFC6&{POP}}}PIZZA.{{\r}} {{\fnNoto Emoji}}🍕{{\fn}}",
    ],
    "spotlight": [
        "HE ATE IT ALL",
        *(
            rf"{{\c&H4DE1FF&{POP_EMPHASIS if word == 'BROTHER' else POP}}}{word}{{\r}}"
            for word in ("WAIT,", "MY", "BROTHER", "ATE", "THE", "PIZZA.")
        ),
    ],
    "ember_box": [
        "HE ATE IT ALL",
        rf"{{\c&HA3E8FF&{POP}}}WAIT,{{\r}}",
        rf"{{\c&HA3E8FF&{POP}}}MY{{\r}} "
        rf"{{\c&H422D2B&\fscx110\fscy110}}BROTHER{{\r}} ATE",
        rf"MY {{\c&HA3E8FF&{POP_EMPHASIS}}}BROTHER{{\r}} ATE",
        rf"MY {{\c&H422D2B&\fscx110\fscy110}}BROTHER{{\r}} "
        rf"{{\c&HA3E8FF&{POP}}}ATE{{\r}}",
        rf"{{\c&HA3E8FF&{POP}}}THE{{\r}}",
        rf"{{\c&HA3E8FF&{POP}}}PIZZA.{{\r}}",
    ],
    "tidal_bounce": [
        "HE ATE IT ALL",
        rf"{{\c&HD4F500&{BOUNCE}}}WAIT,{{\r}}",
        rf"{{\c&HD4F500&{BOUNCE}}}MY{{\r}} "
        rf"{{\c&H40E4FE&\fscx110\fscy110}}BROTHER{{\r}} ATE",
        rf"MY {{\c&HD4F500&{BOUNCE_EMPHASIS}}}BROTHER{{\r}} ATE",
        rf"MY {{\c&H40E4FE&\fscx110\fscy110}}BROTHER{{\r}} "
        rf"{{\c&HD4F500&{BOUNCE}}}ATE{{\r}}",
        rf"{{\c&HD4F500&{BOUNCE}}}THE{{\r}}",
        rf"{{\c&HD4F500&{BOUNCE}}}PIZZA.{{\r}} {{\fnNoto Emoji}}🍕{{\fn}}",
    ],
    "headline_duo": [
        "HE ATE IT ALL",
        rf"{FADE}{{\c&H1C9FFF&}}WAIT,{{\r}}\NMY "
        rf"{{\c&HB6C42E&\fscx110\fscy110}}BROTHER{{\r}} ATE",
        r"WAIT,\N{\c&H1C9FFF&}MY{\r} {\c&HB6C42E&\fscx110\fscy110}BROTHER{\r} ATE",
        r"WAIT,\NMY {\c&H1C9FFF&\fscx110\fscy110}BROTHER{\r} ATE",
        r"WAIT,\NMY {\c&HB6C42E&\fscx110\fscy110}BROTHER{\r} {\c&H1C9FFF&}ATE{\r}",
        rf"{FADE}{{\c&H1C9FFF&}}THE{{\r}}",
        rf"{FADE}{{\c&H1C9FFF&}}PIZZA.{{\r}}",
    ],
    "soft_fade": [
        "He ate it all",
        rf"{FADE}{{\c&HE6F2B8&}}Wait,{{\r}}\Nmy "
        rf"{{\c&HA5D6FF&\fscx110\fscy110}}brother{{\r}} ate the",
        r"Wait,\N{\c&HE6F2B8&}my{\r} {\c&HA5D6FF&\fscx110\fscy110}brother{\r} ate the",
        r"Wait,\Nmy {\c&HE6F2B8&\fscx110\fscy110}brother{\r} ate the",
        r"Wait,\Nmy {\c&HA5D6FF&\fscx110\fscy110}brother{\r} {\c&HE6F2B8&}ate{\r} the",
        r"Wait,\Nmy {\c&HA5D6FF&\fscx110\fscy110}brother{\r} ate {\c&HE6F2B8&}the{\r}",
        rf"{FADE}{{\c&HE6F2B8&}}pizza.{{\r}}",
    ],
    "storyteller": [
        "He ate it all",
        rf"{{\c&HFFDB7F&}}Wait,{{\r}}\N{{{HIDE}}}my{{\r}} "
        rf"{{\c&H6CB8FF&\fscx110\fscy110{HIDE}}}brother{{\r}} {{{HIDE}}}ate{{\r}} "
        rf"{{{HIDE}}}the{{\r}}",
        rf"Wait,\N{{\c&HFFDB7F&}}my{{\r}} {{\c&H6CB8FF&\fscx110\fscy110{HIDE}}}"
        rf"brother{{\r}} {{{HIDE}}}ate{{\r}} {{{HIDE}}}the{{\r}}",
        rf"Wait,\Nmy {{\c&HFFDB7F&\fscx110\fscy110}}brother{{\r}} {{{HIDE}}}ate{{\r}} "
        rf"{{{HIDE}}}the{{\r}}",
        rf"Wait,\Nmy {{\c&H6CB8FF&\fscx110\fscy110}}brother{{\r}} {{\c&HFFDB7F&}}ate"
        rf"{{\r}} {{{HIDE}}}the{{\r}}",
        r"Wait,\Nmy {\c&H6CB8FF&\fscx110\fscy110}brother{\r} ate {\c&HFFDB7F&}the{\r}",
        r"{\c&HFFDB7F&}pizza.{\r}",
    ],
}


def test_there_are_at_least_ten_templates_each_with_its_own_look() -> None:
    assert len(TEMPLATES) >= 10
    # TASK-199's templates are in tests/pipeline/test_caption_styles.
    assert set(EXPECTED) | V1_TEMPLATES <= set(TEMPLATES)
    looks = {
        template.model_dump(exclude={"emoji"}).__repr__()
        for template in TEMPLATES.values()
    }
    assert len(looks) == len(TEMPLATES)
    animations = {template.animation for template in TEMPLATES.values()}
    assert {"none", "pop", "bounce", "fade", "reveal"} <= animations
    assert {template.max_lines for template in TEMPLATES.values()} == {1, 2}


def test_the_schema_has_every_spec_field_and_a_style_can_set_each() -> None:
    fields = [field for names in SCHEMA.values() for field in names]
    assert set(fields) <= set(CaptionTemplate.model_fields)
    clip_only = {"speaker_colors", "word_marks", "translation", "censor"}
    assert set(CaptionStyle.model_fields) - clip_only == set(
        CaptionTemplate.model_fields
    )


@pytest.mark.parametrize("name", list(EXPECTED))
def test_each_template_writes_its_captions_of_the_fixture(
    name: str, tmp_path: Path
) -> None:
    hook, *texts = EXPECTED[name]

    ass = write(tmp_path, make_clip(name))

    assert dialogues(ass) == caption_dialogues(hook, texts)


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_each_template_draws_a_preview_png(name: str, data_dir: Path) -> None:
    path = ensure_preview(name, TEMPLATES[name])

    pixels = png_pixels(path, FRAME)
    width, height = FRAME
    assert pixels.shape == (height, width, 3)
    # The sample caption is drawn in the lower third in its colors.
    lower = pixels[round(0.7 * height) : round(0.8 * height)]
    background = pixels[height // 2, 0]
    changed = np.any(np.abs(lower.astype(int) - background) > 60, axis=2)
    assert changed.sum() > 500, name


def test_the_stroke_and_box_take_the_outline_color(tmp_path: Path) -> None:
    ass = write(tmp_path, make_clip("ember_box"))

    caption = next(line for line in ass.splitlines() if "Style: Caption" in line)
    fields = caption.split(",")
    # OutlineColour (the box), BorderStyle 3 (opaque box), Outline (padding).
    assert (fields[5], fields[15], fields[16]) == ("&H002E57E4", "3", "8.8")


def test_a_clip_style_sets_the_new_fields(tmp_path: Path) -> None:
    style = CaptionStyle(
        font="Inter Bold",
        outline=2,
        outline_color="#112233",
        shadow=0,
        box=False,
        max_lines=2,
        max_words_per_line=2,
        animation="reveal",
        uppercase=False,
    )

    ass = write(tmp_path, make_clip("karaoke_bold", caption_style=style))

    caption = next(line for line in ass.splitlines() if "Style: Caption" in line)
    fields = caption.split(",")
    assert (fields[1], fields[5], fields[15:18]) == (
        "Inter Bold",
        "&H00332211",
        ["1", "2", "0"],
    )
    # Pages of two lines of two words; the words after the spoken one hidden.
    first = dialogues(ass)[1]
    assert first.endswith(
        rf"{{\c&H3FD2FF&}}Wait,{{\r}}\N{{{HIDE}}}my{{\r}} "
        rf"{{\c&H356BFF&\fscx110\fscy110{HIDE}}}brother{{\r}}"
    )


def test_a_style_font_must_be_bundled() -> None:
    assert style_problems(CaptionStyle(font="Montserrat ExtraBold")) == []
    assert style_problems(CaptionStyle()) == []
    assert style_problems(CaptionStyle(font="Comic Sans MS")) == [
        "caption font 'Comic Sans MS' is not a bundled font"
    ]


def test_pages_hold_up_to_max_lines_and_end_at_a_pause() -> None:
    def line(*starts: int) -> list[CaptionWord]:
        return [CaptionWord(str(start), start, start + 200) for start in starts]

    one, two, three = line(0, 200), line(400, 600), line(800)
    after_pause = line(1400)

    assert group_pages([one, two, three], 2) == [[one, two], [three]]
    assert group_pages([one, two, three], 1) == [[one], [two], [three]]
    assert group_pages([one, after_pause], 2) == [[one], [after_pause]]
    assert group_pages([], 2) == []


def test_a_styled_preview_differs_from_the_template_preview(data_dir: Path) -> None:
    template = get_template("minimal")
    plain = ensure_preview("minimal", template).read_bytes()

    styled = styled_preview(template, CaptionStyle(primary_color="#FF0000", size=80))

    assert styled.startswith(b"\x89PNG\r\n\x1a\n")
    assert styled != plain
    assert styled_preview(template, CaptionStyle()) == plain
