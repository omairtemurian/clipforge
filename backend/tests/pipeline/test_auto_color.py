"""Tests of auto color correction in the render (render_graph.COLOR_FILTER)
with ffmpeg: a dull, washed-out clip comes out with more contrast and
saturation, and the filter leaves the graph alone when it is off."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import CropPlan, FaceBox
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.render_graph import COLOR_FILTER, clip_graph
from frames import Pixels, frame_at

CLIP = ClipSpan(1, 0.0, 2.0)
SIZE = (1280, 720)


def plan() -> CropPlan:
    """The crop plan of CLIP with no faces."""
    faces: list[list[FaceBox]] = [[] for _ in sample_times(CLIP.start, CLIP.end)]
    return plan_crop(CLIP, "9:16", SIZE, faces, [])


def stats(pixels: Pixels) -> tuple[float, float]:
    """Return the spread of brightness (standard deviation of the mean of the
    channels) and the mean saturation (max - min channel) of pixels."""
    rgb = pixels.astype(float)
    return float(rgb.mean(axis=2).std()), float((rgb.max(2) - rgb.min(2)).mean())


@pytest.fixture(scope="module")
def dull(sample_mp4: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """2 s of the fixture video with its contrast and saturation halved and
    lifted towards grey."""
    path = tmp_path_factory.mktemp("dull") / "dull.mp4"
    run_ffmpeg(
        ["-ss", "20", "-t", "2", "-i", sample_mp4]
        + ["-vf", "eq=contrast=0.5:saturation=0.5:brightness=0.08"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path]
    )
    return path


def test_auto_color_spreads_levels_and_adds_saturation(
    dull: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    outputs = {}
    for auto_color in (False, True):
        output = tmp_path / f"color-{auto_color}.mp4"
        render_clip(
            dull,
            output,
            CLIP.start,
            CLIP.end,
            plan(),
            "fill",
            render_settings,
            auto_color=auto_color,
        )
        outputs[auto_color] = stats(frame_at(output, 1.0))

    (plain_spread, plain_sat), (color_spread, color_sat) = outputs[False], outputs[True]
    assert color_spread > plain_spread * 1.1
    assert color_sat > plain_sat * 1.2
    assert np.isfinite([color_spread, color_sat]).all()


def test_the_color_filter_is_only_in_the_graph_when_on() -> None:
    off = clip_graph(plan(), "fill", 0.0, (1080, 1920), 30)
    on = clip_graph(plan(), "fill", 0.0, (1080, 1920), 30, auto_color=True)
    assert COLOR_FILTER not in off
    assert f"{COLOR_FILTER}[framed]" not in on
    assert f"[unzoomed]{COLOR_FILTER}[v]" in on
