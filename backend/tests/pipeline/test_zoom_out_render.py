"""Zoomed-out moments render (TASK-198): square_blur and fit at 1080x1920
with the subject region sharp over a blurred background, and the zoom
between a fill scene and a zoomed-out one instead of a hard cut."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import CropPlan, FaceBox
from clipforge.pipeline.layout_parts import square_place
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.scene_framing import add_eases
from clipforge.pipeline.scene_graph import ScenePart
from frames import Pixels, frame_at

FRAME = (1280, 720)
SIZE = (1080, 1920)


@pytest.fixture(scope="module")
def checks(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 6 s 1280x720 video with sound: a fine checkerboard (sharp detail
    that a blur wipes out), the left half darker than the right."""
    path = tmp_path_factory.mktemp("zoom_out") / "checks.mp4"
    video = (
        "color=size=1280x720:rate=30:duration=6,format=gray,"
        "geq=lum='(lt(X,640)*80+120)*mod(floor(X/8)+floor(Y/8),2)+30',"
        "format=yuv420p"
    )
    run_ffmpeg(
        ["-f", "lavfi", "-i", video, "-f", "lavfi", "-i"]
        + ["anullsrc=r=48000:cl=stereo", "-t", "6", "-c:v", "libx264"]
        + ["-crf", "12", "-c:a", "aac", "-shortest", path]
    )
    return path


@pytest.fixture(scope="module")
def waves(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 6 s 1280x720 video with sound: smooth light and dark blobs, which
    a zoom that is a few pixels off barely changes."""
    path = tmp_path_factory.mktemp("zoom_out") / "waves.mp4"
    video = (
        "color=size=1280x720:rate=30:duration=6,format=gray,"
        "geq=lum='128+60*sin(X/40)+60*cos(Y/35)',format=yuv420p"
    )
    run_ffmpeg(
        ["-f", "lavfi", "-i", video, "-f", "lavfi", "-i"]
        + ["anullsrc=r=48000:cl=stereo", "-t", "6", "-c:v", "libx264"]
        + ["-c:a", "aac", "-shortest", path]
    )
    return path


@pytest.fixture(scope="module")
def plan() -> CropPlan:
    """The 9:16 plan of 0-6 s that follows one face at the frame's center."""
    clip = ClipSpan(1, 0.0, 6.0)
    box = FaceBox(x=590, y=310, width=100, height=100, score=0.9, kind="face")
    times = [round(k / 10, 3) for k in range(60)]
    return plan_crop(clip, "9:16", FRAME, [[box] for _ in times], [])


def sharpness(pixels: Pixels) -> float:
    """Return the mean absolute difference between horizontal neighbours."""
    grey = pixels.astype(float).mean(axis=2)
    return float(np.abs(np.diff(grey, axis=1)).mean())


def render(
    plan: CropPlan, parts: list[ScenePart], source: Path, out: Path, s: RenderSettings
) -> Path:
    """Render 0-6 s of source scene by scene as parts into out."""
    video = render_clip(source, out, 0.0, 6.0, plan, "fill", s, scenes=parts)
    info = probe_media(video)
    assert (info.width, info.height) == SIZE
    assert info.duration == pytest.approx(6.0, abs=0.2)
    return video


def test_square_blur_and_fit_show_the_subject_sharp_over_a_blur(
    checks: Path, plan: CropPlan, tmp_path: Path, render_settings: RenderSettings
) -> None:
    parts = [
        ScenePart(0.0, 3.0, plan, "square_blur"),
        ScenePart(3.0, 6.0, plan, "fit"),
    ]
    video = render(plan, parts, checks, tmp_path / "out.mp4", render_settings)
    left, top = square_place(SIZE)
    assert (left, top) == (0, 186)
    square = frame_at(video, 1.5)
    front = square[top + 20 : top + 1060, 20:1060]
    above, below = square[20 : top - 20], square[top + 1100 : 1900]
    assert sharpness(front) > 4 * max(sharpness(above), sharpness(below))
    # The square is the whole frame height: 1080 px for 720, so the 8 px
    # squares are 12 px tall.
    fit = frame_at(video, 4.5)
    middle = fit[680:1240, 20:1060]
    margin = fit[100:600, 20:1060]
    assert sharpness(middle) > 4 * sharpness(margin)


def test_a_zoom_out_next_to_fill_zooms_instead_of_cutting(
    waves: Path, plan: CropPlan, tmp_path: Path, render_settings: RenderSettings
) -> None:
    parts = add_eases(
        [
            ScenePart(0.0, 2.0, plan, "fill"),
            ScenePart(2.0, 4.0, plan, "square_blur"),
            ScenePart(4.0, 6.0, plan, "fill"),
        ],
        FRAME,
        [],
        0.3,
    )
    assert parts[1].ease_in is not None and parts[1].ease_out is not None
    eased = render(plan, parts, waves, tmp_path / "eased.mp4", render_settings)
    hard = [ScenePart(p.start, p.end, p.plan, p.layout) for p in parts]
    cut = render(plan, hard, waves, tmp_path / "cut.mp4", render_settings)

    def jump(video: Path, at: float) -> float:
        before, after = frame_at(video, at - 0.05), frame_at(video, at + 0.05)
        return float(np.abs(before.astype(float) - after.astype(float)).mean())

    for edge in (2.0, 4.0):
        assert jump(eased, edge) < jump(cut, edge) / 2
    # Mid-way through, the zoom-out shows the same frame either way.
    middle = np.abs(frame_at(eased, 3.0).astype(float) - frame_at(cut, 3.0))
    assert float(middle.mean()) < 3


def test_eases_skip_edges_at_scene_cuts_and_non_fill_neighbours(
    plan: CropPlan,
) -> None:
    parts = [
        ScenePart(0.0, 2.0, plan, "fill"),
        ScenePart(2.0, 4.0, plan, "fit"),
        ScenePart(4.0, 6.0, plan, "split"),
    ]
    eased = add_eases(parts, FRAME, [2.02], 0.3)
    assert (eased[1].ease_in, eased[1].ease_out) == (None, None)
    eased = add_eases(parts, FRAME, [], 0.3)
    assert eased[1].ease_in is not None and eased[1].ease_out is None
