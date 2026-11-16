"""The caption templates of TASK-199 (white + green and the other new looks):
the ASS that they write, the colors that any template takes from the owner,
and the pixels libass draws."""

import re
import shutil
from pathlib import Path

import numpy as np
import pytest
from builders import make_clip
from clipforge.captions_templates import CaptionTemplate, get_template, load_templates
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media
from clipforge.models import CaptionStyle, FaceBox
from clipforge.pipeline.caption_effects import bgr
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.captions import ass_time, build_ass, write_captions
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import SIZES, render_clip, render_problems
from clipforge.pipeline.step import TRANSCRIPT
from fakes import FIXTURES
from frames import Pixels, caption_frame, frame_at

NEW_TEMPLATES = {
    "snow_lime": "none",
    "snow_sun": "none",
    "snow_ember": "none",
    "pill_pop": "pill",
    "single_slam": "pop",
    "underline_duo": "underline",
    "hollow_fill": "hollow",
    "neon_lime": "none",
    "typewriter": "reveal",
    "bounce_in": "bounce",
    "shake_hype": "shake",
    "lowercase_calm": "none",
    "marker_note": "pop",
    "big_guy": "pop",
    "block_sign": "none",
    "passion_burn": "none",
    "titan_pop": "pop",
}
# Names of other caption tools that no template of ours may be called after.
OTHER_TOOLS = ("hormozi", "submagic", "capcut", "opus", "veed", "alex", "mrbeast")
SIZE = (540, 960)
# "is" is the active word from 400 to 800 ms, "funny" the emphasis word.
WORDS = [
    CaptionWord("This", 0, 400),
    CaptionWord("is", 400, 800),
    CaptionWord("funny", 800, 1300),
    CaptionWord("you", 1300, 1600),
]
TAGGED = re.compile(r"\{([^{}]*)\}([^{}\\]+)\{\\r\}")
GREEN = "#22C55E"


def events(template: CaptionTemplate) -> dict[int, str]:
    """Return the text of each Dialogue event of the caption of WORDS, by the
    start in ms of the active word."""
    ass = build_ass(WORDS, template, SIZE, emphasis_words=("funny",), emoji_map={})
    found = {}
    for word in WORDS:
        start = f"Dialogue: 0,{ass_time(word.start)},"
        (line,) = [line for line in ass.splitlines() if line.startswith(start)]
        found[word.start] = line.split(",,0,0,0,,", 1)[1]
    return found


def tagged(text: str, tag: str) -> list[str]:
    """Return the words of text whose override block holds tag."""
    return [word for block, word in TAGGED.findall(text) if tag in block]


def test_there_are_at_least_twelve_new_templates_and_26_in_all() -> None:
    templates = load_templates()

    assert len(NEW_TEMPLATES) >= 12
    assert set(NEW_TEMPLATES) <= set(templates)
    assert len(templates) >= 26
    for name in NEW_TEMPLATES:
        assert not any(tool in name for tool in OTHER_TOOLS), name
        assert templates[name].animation == NEW_TEMPLATES[name], name


@pytest.mark.parametrize("name", sorted(NEW_TEMPLATES))
def test_the_active_word_alone_gets_the_highlight_color(name: str) -> None:
    template = get_template(name)
    highlight = f"&H{bgr(template.highlight_color)}&"
    # A pill template keeps the word's color and puts the highlight behind it.
    tag = f"\\3c{highlight}" if template.animation == "pill" else f"\\c{highlight}"

    for start, text in events(template).items():
        active = next(word for word in WORDS if word.start == start)
        shown = active.text.upper() if template.uppercase else active.text
        assert tagged(text, tag) == [shown], (name, start, text)
        assert text.count(highlight) == 1, (name, start, text)


def test_white_words_with_a_green_spoken_word() -> None:
    template = get_template("snow_lime").styled(
        CaptionStyle(highlight_color=GREEN, primary_color="#FFFFFF")
    )

    ass = build_ass(WORDS, template, SIZE, emoji_map={})

    assert "Style: Caption,Poppins Black,70,&H00FFFFFF," in ass
    text = events(template)[400]
    assert tagged(text, f"\\c&H{bgr(GREEN)}&") == ["is"]
    assert "5EC522" in text and "FFFFFF" not in text


@pytest.mark.parametrize("name", sorted(load_templates()))
def test_any_template_takes_the_base_and_active_colors(name: str) -> None:
    template = get_template(name).styled(
        CaptionStyle(primary_color="#FFFFFF", highlight_color=GREEN)
    )
    ass = build_ass(WORDS, template, SIZE, emoji_map={})

    style = next(line for line in ass.splitlines() if line.startswith("Style: Caption"))
    assert ",&H00FFFFFF,&H0022C55E".replace("22C55E", "5EC522") in style
    active = events(template)[400]
    # Highlight as the fill of the spoken word, or behind it on a pill.
    assert f"&H{bgr(GREEN)}&" in active


def test_underline_marks_the_spoken_word_only() -> None:
    text = events(get_template("underline_duo"))

    assert tagged(text[400], "\\u1") == ["is"]
    assert tagged(text[0], "\\u1") == ["This"]
    assert "\\u1" not in "".join(
        block for block, word in TAGGED.findall(text[800]) if word != "funny"
    )


def test_pill_puts_the_highlight_behind_the_spoken_word_only() -> None:
    template = get_template("pill_pop")
    text = events(template)[400]

    assert tagged(text, "\\bord") == ["is"]
    assert f"\\3c&H{bgr(template.highlight_color)}&\\bord8" in text
    assert tagged(text, f"\\c&H{bgr(template.primary_color)}&") == ["is"]


def test_hollow_draws_the_other_words_as_outlines() -> None:
    template = get_template("hollow_fill")
    text = events(template)[400]

    # The page holds three words: This is funny.
    assert sorted(tagged(text, "\\1a&HFF&")) == ["FUNNY", "THIS"]
    assert tagged(text, f"\\c&H{bgr(template.highlight_color)}&") == ["IS"]
    # The emphasis word's stroke is in its color, the others' in the primary.
    assert tagged(text, f"\\3c&H{bgr(template.emphasis_color)}&") == ["FUNNY"]
    assert tagged(text, f"\\3c&H{bgr(template.primary_color)}&") == ["THIS"]


def test_shake_swings_the_spoken_emphasis_word_only() -> None:
    text = events(get_template("shake_hype"))

    assert tagged(text[800], "\\frz4") == ["FUNNY"]
    assert all("\\frz" not in text[start] for start in (0, 400, 1300))


def test_typewriter_hides_the_words_not_yet_spoken() -> None:
    text = events(get_template("typewriter"))

    assert tagged(text[400], "\\alpha&HFF&") == ["FUNNY", "YOU"]
    assert tagged(text[1300], "\\alpha&HFF&") == []


def test_bounce_and_pop_animate_the_spoken_word_only() -> None:
    for name, word in (("bounce_in", "is"), ("single_slam", "IS")):
        text = events(get_template(name))
        assert tagged(text[400], "\\t(") == [word], name


def near(pixels: Pixels, color: str, tolerance: int) -> Pixels:
    """Return the mask of the pixels within tolerance of color in every
    channel."""
    wanted = np.array([int(color[i : i + 2], 16) for i in (1, 3, 5)])
    return np.abs(pixels.astype(int) - wanted).max(axis=2) <= tolerance


def test_libass_draws_the_spoken_word_green_and_the_others_white(
    tmp_path: Path,
) -> None:
    template = get_template("snow_lime")
    ass = tmp_path / "snow_lime.ass"
    ass.write_text(build_ass(WORDS, template, SIZE, emoji_map={}), encoding="utf-8")

    first = caption_frame(ass, SIZE, 0.2)
    second = caption_frame(ass, SIZE, 0.6)

    # Colors on black, drawn at full size: within 12 of the template's in
    # each channel (libass anti-aliases only the glyph edges).
    for pixels in (first, second):
        assert near(pixels, GREEN, 12).sum() > 150
        assert near(pixels, "#FFFFFF", 12).sum() > 150
    columns = [
        np.flatnonzero(near(pixels, GREEN, 12).any(axis=0)).mean()
        for pixels in (first, second)
    ]
    assert columns[1] > columns[0] + 40


def test_libass_shakes_the_spoken_emphasis_word_in_place(tmp_path: Path) -> None:
    ass = tmp_path / "shake.ass"
    ass.write_text(
        build_ass(
            WORDS[:3],
            get_template("shake_hype"),
            SIZE,
            emphasis_words=("funny",),
            emoji_map={},
        ),
        encoding="utf-8",
    )

    swinging = caption_frame(ass, SIZE, 0.84).astype(int)
    settled = caption_frame(ass, SIZE, 1.1).astype(int)

    changed = np.abs(swinging - settled).max(axis=2) > 64
    columns = np.flatnonzero(changed.any(axis=0))
    drawn = np.flatnonzero((settled.max(axis=2) > 64).any(axis=0))
    # Only the right word (FUNNY) moves: the words before it stay put.
    assert columns.size > 20
    assert columns.min() > drawn.min() + 0.4 * (drawn.max() - drawn.min())


def test_a_clip_rendered_in_snow_lime_shows_the_spoken_word_in_green(
    sample_mp4: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    # Clip 1 of the fixture, 0.5-8.5 s: "the" is the active word from 2.95 s
    # (in clip times). The green is within 40 per channel of GREEN: the
    # encoder's chroma subsampling and compression blur the colors of thin
    # glyph edges, and the pixels counted are those inside the glyphs.
    span = ClipSpan(1, 0.5, 8.5)
    shutil.copy(FIXTURES / "transcript.json", tmp_path / TRANSCRIPT)
    faces: list[list[FaceBox]] = [[] for _ in sample_times(span.start, span.end)]
    plan = plan_crop(span, "9:16", (1280, 720), faces, [])
    clip = make_clip("snow_lime", id=1, start=span.start, end=span.end)
    fps = render_settings.fps
    captions = write_captions(tmp_path, clip, SIZES["9:16"], fps)

    video = render_clip(
        sample_mp4,
        tmp_path / "snow_lime.mp4",
        span.start,
        span.end,
        plan,
        "fill",
        render_settings,
        captions=captions,
    )

    info = probe_media(video)
    assert render_problems(info, SIZES["9:16"], span.end - span.start) == []
    pixels = frame_at(video, 3.0)
    height = len(pixels)
    band = pixels[round(0.66 * height) : round(0.80 * height)]
    assert near(band, GREEN, 40).sum() > 300
    # Away from the captions no pixel is that green.
    assert near(pixels[: round(0.5 * height)], GREEN, 15).sum() < 50
