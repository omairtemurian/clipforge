"""Tests that a render honors the editor's crop tool and fit background
(pipeline/framing), the clip's auto zoom (pipeline/zoom_graph) and its
scenes (pipeline/scene_framing): the frames of a clip of a four-color
video."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import (
    CropPlan,
    CropPoint,
    FaceBox,
    Framing,
    SceneReframe,
    ZoomKeyframe,
)
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.framing import apply_crop_tool
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.scene_framing import keyframed_plan
from clipforge.pipeline.scene_graph import ScenePart
from frames import Pixels, frame_at

# Top left red, top right blue, bottom left yellow, bottom right cyan.
RED, BLUE, YELLOW, CYAN = (255, 0, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255)
CLIP = ClipSpan(1, 10.0, 14.0)
SIZE = (216, 384)


@pytest.fixture(scope="module")
def quadrants(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 16 s 1280x720 video with sound whose quarters are 4 colors."""
    path = tmp_path_factory.mktemp("quadrants") / "quadrants.mp4"
    video = (
        "color=size=1280x720:rate=30:duration=16,format=gbrp,"
        "geq=r='255*lt(X,640)':g='255*gte(Y,360)':b='255*gte(X,640)',"
        "format=yuv420p"
    )
    run_ffmpeg(
        ["-f", "lavfi", "-i", video, "-f", "lavfi", "-i"]
        + ["anullsrc=r=48000:cl=stereo", "-t", "16", "-c:v", "libx264"]
        + ["-c:a", "aac", "-shortest", path]
    )
    return path


def centered_plan() -> CropPlan:
    """The 9:16 plan of CLIP with no faces: a window across all 4 colors."""
    no_faces: list[list[FaceBox]] = [[] for _ in sample_times(CLIP.start, CLIP.end)]
    return plan_crop(CLIP, "9:16", (1280, 720), no_faces, [])


def middle(frame: Pixels) -> Pixels:
    """Return the mean color of the middle half of frame."""
    height, width, _ = frame.shape
    part = frame[height // 4 : height * 3 // 4, width // 4 : width * 3 // 4]
    return part.reshape(-1, 3).mean(axis=0)


def near(color: Pixels, expected: tuple[int, int, int]) -> bool:
    """Return True if each channel of color is within 40 of expected."""
    return bool(np.all(np.abs(color.astype(int) - expected) <= 40))


def test_a_render_follows_the_crop_tool_keyframes(
    quadrants: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    framing = Framing(
        scale=0.5,
        tracker=False,
        points=[
            CropPoint(t=10.0, x=0.2, y=0.25),
            CropPoint(t=11.0, x=0.2, y=0.25),
            CropPoint(t=13.0, x=0.8, y=0.75),
        ],
    )
    plan = apply_crop_tool(centered_plan(), framing, (1280, 720))
    output = tmp_path / "framed.mp4"

    render_clip(
        quadrants,
        output,
        CLIP.start,
        CLIP.end,
        plan,
        "fill",
        render_settings,
        size=SIZE,
    )

    info = probe_media(output)
    assert (info.width, info.height) == SIZE
    assert near(middle(frame_at(output, 0.5)), RED)
    assert near(middle(frame_at(output, 3.5)), CYAN)


def test_a_point_with_the_tracker_on_moves_the_window_there(
    quadrants: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    framing = Framing(scale=0.5, points=[CropPoint(t=12.0, x=0.8, y=0.25)])
    plan = apply_crop_tool(centered_plan(), framing, (1280, 720))
    output = tmp_path / "tracked.mp4"

    render_clip(
        quadrants,
        output,
        CLIP.start,
        CLIP.end,
        plan,
        "fill",
        render_settings,
        size=SIZE,
    )

    assert near(middle(frame_at(output, 2.0)), BLUE)


def test_the_fit_layout_can_show_black_around_the_video(
    quadrants: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    plan = centered_plan().model_copy(update={"background": "black"})
    output = tmp_path / "fit.mp4"

    render_clip(
        quadrants,
        output,
        CLIP.start,
        CLIP.end,
        plan,
        "fit",
        render_settings,
        size=SIZE,
    )

    frame = frame_at(output, 1.0)
    assert (probe_media(output).width, probe_media(output).height) == SIZE
    assert near(frame[10, SIZE[0] // 2], (0, 0, 0))
    assert near(frame[SIZE[1] // 2 - 20, 20], RED)
    assert near(frame[SIZE[1] // 2 + 20, SIZE[0] - 20], CYAN)
    assert near(frame[SIZE[1] // 2 + 20, 20], YELLOW)


def test_a_punch_in_zooms_about_the_subject_and_keeps_the_size(
    quadrants: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    # A face in the top left quarter of the window: the zoom keeps the top
    # left corner, so the red/blue edge (the middle) moves right by 15%.
    plan = centered_plan()
    keyframes = [
        k.model_copy(
            update={
                "faces": [
                    FaceBox(x=k.x, y=0, width=plan.width / 2, height=360, score=0.9)
                ]
            }
        )
        for k in plan.keyframes
    ]
    plan = plan.model_copy(update={"keyframes": keyframes})
    zoom = [
        ZoomKeyframe(t=10.5, scale=1.0),
        ZoomKeyframe(t=11.0, scale=1.15),
        ZoomKeyframe(t=13.0, scale=1.15),
        ZoomKeyframe(t=13.5, scale=1.0),
    ]
    plain, zoomed = tmp_path / "plain.mp4", tmp_path / "zoomed.mp4"

    for output, keys in ((plain, []), (zoomed, zoom)):
        render_clip(
            quadrants, output, CLIP.start, CLIP.end, plan, "fill", render_settings,
            size=SIZE, zoom=keys,
        )  # fmt: skip

    info = probe_media(zoomed)
    assert (info.width, info.height) == SIZE
    assert info.duration == pytest.approx(probe_media(plain).duration, abs=0.05)
    column, row = SIZE[0] * 54 // 100, SIZE[1] // 10
    assert near(frame_at(plain, 2.0)[row, column], BLUE)
    assert near(frame_at(zoomed, 2.0)[row, column], RED)
    # Before and after the punch-in, the frames are the same.
    assert near(frame_at(zoomed, 0.2)[row, column], BLUE)
    assert near(frame_at(zoomed, 3.8)[row, column], BLUE)


def fixed(start: float, end: float, x: float) -> ScenePart:
    """A fill scene of CLIP from start to end seconds whose half-size window
    is fixed with its center at x (fraction of the width), in the top half."""
    scene = SceneReframe(
        start=start,
        end=end,
        mode="fixed",
        scale=0.5,
        crop_keyframes=[CropPoint(t=start, x=x, y=0.25)],
    )
    plan = keyframed_plan(centered_plan(), centered_plan(), scene, (1280, 720))
    return ScenePart(start, end, plan, "fill")


def test_fixed_crops_at_the_left_and_right_edge_render_differently(
    quadrants: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    left, right = tmp_path / "left.mp4", tmp_path / "right.mp4"
    plan = centered_plan()

    for output, x in ((left, 0.0), (right, 1.0)):
        scene = fixed(CLIP.start, CLIP.end, x)
        render_clip(
            quadrants, output, CLIP.start, CLIP.end, plan, "fill", render_settings,
            size=SIZE, scenes=[scene],
        )  # fmt: skip

    assert near(middle(frame_at(left, 1.0)), RED)
    assert near(middle(frame_at(right, 1.0)), BLUE)
    assert not np.array_equal(frame_at(left, 1.0), frame_at(right, 1.0))


def test_each_scene_is_framed_on_its_own_without_easing_across_a_cut(
    quadrants: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    plan = centered_plan().model_copy(update={"background": "black"})
    scenes = [
        ScenePart(10.0, 11.5, plan, "fit"),
        fixed(11.5, 12.5, 0.0),
        fixed(12.5, 14.0, 1.0),
    ]
    output = tmp_path / "scenes.mp4"

    render_clip(
        quadrants, output, CLIP.start, CLIP.end, plan, "fill", render_settings,
        size=SIZE, cut_ranges=[(13.4, 13.6)], scenes=scenes,
    )  # fmt: skip

    info = probe_media(output)
    assert (info.width, info.height) == SIZE
    assert info.duration == pytest.approx(3.8, abs=0.05)
    assert near(frame_at(output, 0.5)[10, SIZE[0] // 2], (0, 0, 0))
    assert near(middle(frame_at(output, 1.6)), RED)
    assert near(middle(frame_at(output, 2.45)), RED)
    assert near(middle(frame_at(output, 2.55)), BLUE)
    assert near(middle(frame_at(output, 3.6)), BLUE)
