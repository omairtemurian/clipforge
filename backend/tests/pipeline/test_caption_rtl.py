"""Tests of right-to-left captions (SPEC-v2 3.4): Persian, Arabic and Hebrew
caption text is drawn in a bundled font of its script (Vazirmatn, Noto Sans
Hebrew) with an auto base direction, and libass (HarfBuzz + FriBidi) shapes
and orders it.

Shaping and order are checked against the same caption written in visual
order: Unicode presentation forms (the joined glyphs) in a left-to-right
override (U+202D ... U+202C), which libass draws as written."""

from pathlib import Path

import numpy as np
import pytest
from builders import SIX, make_clip
from caption_fakes import dialogues
from clipforge.captions_templates import get_template, load_emoji_map
from clipforge.ffmpeg import run_ffmpeg
from clipforge.fonts import covering_font
from clipforge.models import CaptionCue, CaptionStyle, CaptionTranslation, Transcript
from clipforge.pipeline.caption_effects import encoding
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.captions import build_ass, write_captions
from clipforge.pipeline.render_graph import subtitles_filter
from clipforge.pipeline.step import TRANSCRIPT, write_json
from frames import Pixels, caption_frame, drawn_extent

FRAME = (540, 300)
LRO, PDF = "\u202d", "\u202c"
VAZIRMATN, HEBREW = "Vazirmatn Bold", "Noto Sans Hebrew Bold"
# (caption text, the font it is drawn in, its visual order with joined
# forms, the same letters unjoined or in the wrong order).
CASES = {
    "persian": (
        "سلام!",
        VAZIRMATN,
        f"{LRO}!\ufee1\ufefc\ufeb3{PDF}",
        f"{LRO}!\ufee1\ufe8d\ufedd\ufeb1{PDF}",
    ),
    "arabic": (
        "مرحبا",
        VAZIRMATN,
        f"{LRO}\ufe8e\ufe92\ufea3\ufeae\ufee3{PDF}",
        f"{LRO}\ufe8d\ufe8f\ufea1\ufead\ufee1{PDF}",
    ),
    "hebrew": ("שלום!", HEBREW, f"{LRO}!םולש{PDF}", f"{LRO}שלום!{PDF}"),
}
# libass's log line when it picks a font for a style (Bold 0: weight 400).
FONTSELECT = "fontselect: ({font}, 400, 0) -> {file}, 0, {file}"


def ass_of(text: str, tmp_path: Path, name: str = "c.ass") -> Path:
    """Write the captions of one word, text, active from 0 to 2 s in the
    minimal template, on FRAME, and return the file."""
    ass = build_ass(
        [CaptionWord(text, 0, 2000)],
        get_template("minimal"),
        FRAME,
        emoji_map=load_emoji_map(),
    )
    path = tmp_path / name
    path.write_text(ass, encoding="utf-8")
    return path


def drawn(text: str, tmp_path: Path, name: str = "c.ass") -> Pixels:
    """Return the frame at 1 s of text's captions (ass_of) as libass draws
    them, in signed integers."""
    return caption_frame(ass_of(text, tmp_path, name), FRAME, 1.0).astype(np.int16)


def difference(first: Pixels, second: Pixels) -> float:
    """Return the mean absolute difference of two frames' channels."""
    return float(np.abs(first - second).mean())


@pytest.mark.parametrize(
    ("text", "font"),
    [
        ("Wait, my brother ate the pizza.", "Inter Bold"),
        ("سلام دنیا، چطوری؟", VAZIRMATN),
        ("مرحبا بالعالم", VAZIRMATN),
        ("שלום עולם", HEBREW),
        ("Pizza پیتزا 2024", VAZIRMATN),
        ("🍕", "Inter Bold"),
    ],
)
def test_a_script_the_template_font_lacks_gets_a_bundled_font_of_it(
    text: str, font: str
) -> None:
    assert covering_font("Inter Bold", text) == font


def test_a_font_that_is_not_available_stays() -> None:
    assert covering_font("No Such Font", "سلام") == "No Such Font"


@pytest.mark.parametrize(
    ("text", "value"),
    [("سلام!", -1), ("مرحبا", -1), ("שלום", -1), ("Hello, پیتزا", -1), ("Hi!", 1)],
)
def test_right_to_left_text_gets_an_auto_base_direction(text: str, value: int) -> None:
    assert encoding(text) == value


def test_the_style_of_persian_captions_names_vazirmatn_and_auto_direction(
    tmp_path: Path,
) -> None:
    ass = ass_of("سلام!", tmp_path).read_text(encoding="utf-8")

    assert "Style: Caption,Vazirmatn Bold,40," in ass
    assert ass.split("Style: Caption,")[1].splitlines()[0].endswith(",-1")
    assert "Style: Hook,Inter Bold,28," in ass
    assert ass.split("Style: Hook,")[1].splitlines()[0].endswith(",1")


@pytest.mark.parametrize("case", sorted(CASES))
def test_libass_shapes_and_orders_right_to_left_captions(
    case: str, tmp_path: Path
) -> None:
    text, _, visual, wrong = CASES[case]

    shown = drawn(text, tmp_path, "text.ass")

    width, height = drawn_extent(shown.astype(np.uint8))
    assert width > 40 and height > 15
    assert difference(shown, drawn(visual, tmp_path, "visual.ass")) < 0.15
    assert difference(shown, drawn(wrong, tmp_path, "wrong.ass")) > 0.5


@pytest.mark.parametrize("case", sorted(CASES))
def test_libass_draws_every_glyph_from_the_bundled_font(
    case: str, tmp_path: Path
) -> None:
    text, font, _, _ = CASES[case]
    ass = ass_of(text, tmp_path)

    result = run_ffmpeg(
        ["-f", "lavfi", "-i", f"color=size={FRAME[0]}x{FRAME[1]}:rate=2:duration=1"]
        + ["-vf", subtitles_filter(ass), "-f", "null", "-"],
        loglevel="info",
    )

    log = result.stderr.decode()
    file = {VAZIRMATN: "Vazirmatn-Bold", HEBREW: "NotoSansHebrew-Bold"}[font]
    assert FONTSELECT.format(font=font, file=file) in log
    assert "Glyph 0x" not in log


def test_a_persian_translation_renders_right_to_left_in_vazirmatn(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / TRANSCRIPT,
        Transcript(language="en", duration=60, segments=[SIX]),
    )
    translation = CaptionTranslation(
        language="fa",
        cues=[CaptionCue(start=10.0, end=11.25, text="سلام دنیا!", speaker="S0")],
    )
    clip = make_clip("minimal", caption_style=CaptionStyle(translation=translation))

    path = write_captions(tmp_path, clip, FRAME, 30)

    ass = path.read_text(encoding="utf-8")
    assert "Style: Caption,Vazirmatn Bold,40," in ass
    texts = [line.split(",,0,0,0,,")[1] for line in dialogues(ass)[1:]]
    assert texts == [r"{\c&HFFFFFF&}سلام{\r} دنیا!", r"سلام {\c&HFFFFFF&}دنیا!{\r}"]
    width, _ = drawn_extent(caption_frame(path, FRAME, 1.0))
    assert width > 60
