"""Unit tests of the minimal render: the center crop, the checks, the paths."""

from dataclasses import replace
from pathlib import Path

import pytest
from clipforge.config import Settings
from clipforge.ffmpeg import MediaInfo
from clipforge.pipeline.render import Crop, center_crop, clip_output, render_problems

OUTPUT_SIZES = [(1080, 1920), (1080, 1080), (1920, 1080)]
GOOD = MediaInfo(
    duration=34.7,
    width=1080,
    height=1920,
    fps=30.0,
    video_codec="h264",
    pix_fmt="yuv420p",
    audio_codec="aac",
    sample_rate=48_000,
    channels=1,
    title=None,
)


@pytest.mark.parametrize(
    ("source", "size", "crop"),
    [
        ((1280, 720), (1080, 1920), Crop(404, 720, 438, 0)),
        ((1280, 720), (1080, 1080), Crop(720, 720, 280, 0)),
        ((1280, 720), (1920, 1080), Crop(1280, 720, 0, 0)),
        ((720, 1280), (1080, 1920), Crop(720, 1280, 0, 0)),
        ((720, 1280), (1080, 1080), Crop(720, 720, 0, 280)),
        ((720, 1280), (1920, 1080), Crop(720, 404, 0, 438)),
        ((1281, 721), (1920, 1080), Crop(1280, 720, 0, 0)),
        ((1920, 1080), (1080, 1920), Crop(606, 1080, 656, 0)),
    ],
)
def test_center_crop_exact_windows(
    source: tuple[int, int], size: tuple[int, int], crop: Crop
) -> None:
    assert center_crop(*source, *size) == crop


@pytest.mark.parametrize("source", [(1280, 720), (853, 480), (641, 359), (1000, 999)])
@pytest.mark.parametrize("size", OUTPUT_SIZES)
def test_center_crop_is_even_centered_and_has_the_output_shape(
    source: tuple[int, int], size: tuple[int, int]
) -> None:
    (src_width, src_height), (width, height) = source, size

    crop = center_crop(src_width, src_height, width, height)

    assert crop.width % 2 == crop.height % 2 == crop.x % 2 == crop.y % 2 == 0
    assert crop.x + crop.width <= src_width and crop.y + crop.height <= src_height
    assert abs(crop.x - (src_width - crop.width - crop.x)) <= 3
    assert abs(crop.y - (src_height - crop.height - crop.y)) <= 3
    assert src_width - crop.width < 2 or src_height - crop.height < 2
    assert crop.width / crop.height == pytest.approx(width / height, rel=0.01)


def test_a_good_render_has_no_problems() -> None:
    assert render_problems(GOOD, (1080, 1920), 34.7) == []
    assert render_problems(GOOD, (1080, 1920), 34.5) == []
    assert render_problems(GOOD, (1080, 1920), 34.9) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"width": 1078}, "size 1078x1920 is not 1080x1920"),
        ({"duration": 34.901}, "duration 34.901s is not 34.700s (±0.2s)"),
        ({"duration": 34.45}, "duration 34.450s is not 34.700s (±0.2s)"),
        ({"video_codec": "hevc"}, "video hevc yuv420p is not h264 yuv420p"),
        ({"pix_fmt": "yuv444p"}, "video h264 yuv444p is not h264 yuv420p"),
        ({"audio_codec": None}, "audio None is not aac"),
    ],
)
def test_render_problems_name_what_is_wrong(
    change: dict[str, object], problem: str
) -> None:
    info = replace(GOOD, **change)

    assert render_problems(info, (1080, 1920), 34.7) == [problem]


def test_clip_output_is_under_the_project_in_data_dir(
    data_dir: Path, tmp_path: Path
) -> None:
    assert clip_output(3, 12) == data_dir / "output" / "3" / "12.mp4"
    other = Settings(data_dir=tmp_path / "other")
    assert clip_output(3, 12, other) == tmp_path / "other" / "output" / "3" / "12.mp4"
