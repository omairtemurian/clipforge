"""Tests of a clip's caption_style (SPEC 8.4): the fields that it sets
replace the template's in the captions and the preview key."""

from pathlib import Path

from builders import SIX, make_clip
from clipforge.captions_templates import clip_template, get_template
from clipforge.models import (
    CaptionStyle,
    Clip,
    CropKeyframe,
    CropPlan,
    CropWindow,
    Transcript,
)
from clipforge.pipeline.captions import write_captions
from clipforge.pipeline.step import TRANSCRIPT, write_json
from clipforge.preview import preview_key


def ass_of(clip: Clip, tmp_path: Path) -> list[str]:
    """Return the lines of the captions that write_captions writes for clip."""
    transcript = Transcript(language="en", duration=60.0, segments=[SIX])
    write_json(tmp_path / TRANSCRIPT, transcript)
    return write_captions(tmp_path, clip, (1080, 1920), 30).read_text().splitlines()


def test_an_empty_style_keeps_the_template() -> None:
    clip = make_clip("neon")

    assert clip_template(clip) == get_template("neon")


def test_a_style_replaces_only_the_fields_it_sets() -> None:
    style = CaptionStyle(size=72, primary_color="#112233", uppercase=False)
    clip = make_clip("neon", caption_style=style)

    template = clip_template(clip)

    base = get_template("neon")
    assert (template.size, template.primary_color, template.uppercase) == (
        72,
        "#112233",
        False,
    )
    assert template.model_copy(
        update={"size": base.size, "primary_color": base.primary_color}
    ) == base.model_copy(update={"uppercase": False})


def test_the_captions_use_the_style(tmp_path: Path) -> None:
    style = CaptionStyle(size=72, position="bottom", uppercase=False)
    lines = ass_of(make_clip("comic", caption_style=style), tmp_path)

    caption_style = next(line for line in lines if line.startswith("Style: Caption"))
    fields = caption_style.split(",")
    assert fields[2] == "72"
    assert fields[18] == "2"
    assert any("pizza." in line for line in lines)
    assert not any("PIZZA" in line for line in lines)


def test_the_preview_key_changes_with_the_style() -> None:
    window = CropWindow(width=404, height=8, y=0, xs=[0])
    plan = CropPlan(
        clip_id=1,
        start=10.0,
        end=12.0,
        aspect="9:16",
        width=404,
        height=8,
        y=0,
        keyframes=[CropKeyframe(t=10.0, x=0, faces=[])],
        layout="fill",
        split=(window, window),
    )
    base = make_clip("neon")
    styled = make_clip("neon", caption_style=CaptionStyle(emoji=True))

    assert preview_key(base, plan) != preview_key(styled, plan)
    assert preview_key(base, plan) == preview_key(make_clip("neon"), plan)
