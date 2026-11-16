"""Aspect ratios (SPEC-v2 3.3): the presets 9:16, 1:1, 4:5, 16:9 and custom
W:H render at the right even size, with the right shape of crop, and the
ratio is validated everywhere it comes in."""

from pathlib import Path

import pytest
from clipforge.aspect import PRESETS, aspect_size, check_aspect
from clipforge.cli import build_parser
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media
from clipforge.models import CropPlan, FaceBox, Framing, Layout, ProcessingSettings
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from pydantic import ValidationError

CLIP = ClipSpan(1, 1.0, 4.0)
SOURCE_SIZE = (1280, 720)
SIZES = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
    "3:2": (1620, 1080),
    "2:3": (1080, 1620),
    "21:9": (1920, 822),
    "1:3": (640, 1920),
    "4:1": (1920, 480),
    "1:4": (480, 1920),
}


def plan_for(aspect: str) -> CropPlan:
    no_faces: list[list[FaceBox]] = [[] for _ in sample_times(CLIP.start, CLIP.end)]
    return plan_crop(CLIP, aspect, SOURCE_SIZE, no_faces, [])


@pytest.mark.parametrize("aspect", ["9:16", "1:1", "4:5", "16:9", "3:2", "2:3"])
def test_presets_and_custom_ratios_render_at_their_size(
    aspect: str, sample_mp4: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    output = render_clip(
        sample_mp4,
        tmp_path / "out.mp4",
        CLIP.start,
        CLIP.end,
        plan_for(aspect),
        "fill",
        render_settings,
    )

    info = probe_media(output)

    assert (info.width, info.height) == SIZES[aspect]
    assert info.width % 2 == info.height % 2 == 0
    assert info.duration == pytest.approx(CLIP.end - CLIP.start, abs=0.2)


@pytest.mark.parametrize("layout", ["fit", "split"])
def test_the_4_5_layouts_render_at_1080x1350(
    layout: Layout, sample_mp4: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    output = render_clip(
        sample_mp4,
        tmp_path / "out.mp4",
        CLIP.start,
        CLIP.end,
        plan_for("4:5"),
        layout,
        render_settings,
    )

    info = probe_media(output)

    assert (info.width, info.height) == (1080, 1350)
    assert info.duration == pytest.approx(CLIP.end - CLIP.start, abs=0.2)


def test_the_4_5_fill_window_has_that_shape() -> None:
    plan = plan_for("4:5")

    assert plan.width / plan.height == pytest.approx(4 / 5, rel=0.01)
    assert plan.height == SOURCE_SIZE[1]


def test_aspect_sizes_are_even_and_keep_the_ratio() -> None:
    for aspect, size in SIZES.items():
        assert aspect_size(aspect) == size
    for aspect in ["7:5", "13:17", "999:300", "5:7"]:
        width, height = aspect_size(aspect)
        assert width % 2 == height % 2 == 0
        assert max(width, height) <= 1920
        ratio = int(aspect.split(":")[0]) / int(aspect.split(":")[1])
        assert width / height == pytest.approx(ratio, rel=0.01)


def test_the_presets_are_the_four_ratios() -> None:
    assert PRESETS == ("9:16", "1:1", "4:5", "16:9")


@pytest.mark.parametrize(
    "aspect",
    ["", "9", "9:", ":16", "0:5", "5:0", "a:b", "9:16:1", "1:5", "5:1", "-1:2"],
)
def test_bad_ratios_are_rejected(aspect: str) -> None:
    with pytest.raises(ValueError):
        check_aspect(aspect)
    with pytest.raises(ValidationError):
        ProcessingSettings(aspect=aspect)
    with pytest.raises(ValidationError):
        Framing(aspect=aspect)


def test_settings_and_framing_accept_4_5_and_custom() -> None:
    assert ProcessingSettings(aspect="4:5").aspect == "4:5"
    assert ProcessingSettings(aspect="7:5").aspect == "7:5"
    assert Framing(aspect="3:4").aspect == "3:4"


def test_the_cli_takes_a_preset_or_custom_ratio(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()

    assert parser.parse_args(["run", "v.mp4", "--aspect", "4:5"]).aspect == "4:5"
    assert parser.parse_args(["run", "v.mp4", "--aspect", "7:5"]).aspect == "7:5"
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "v.mp4", "--aspect", "1:9"])
    assert "more than 4:1" in capsys.readouterr().err
