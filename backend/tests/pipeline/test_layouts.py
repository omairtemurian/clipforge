"""Tests of the clip layouts (SPEC 6.8, 6.11) rendered with ffmpeg: the crop
x expression of a moving window at every frame, and the frames of each
layout of a clip of the fixture."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import CropKeyframe, CropPlan, CropWindow, FaceBox, Layout
from clipforge.pipeline.layout_parts import crop_window, window_x
from clipforge.pipeline.layouts import nudge_plan
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from frames import Pixels, frame_at

GRADIENT_WIDTH = 1280
# The 4 s clip of the fixture that the layouts render.
CLIP = ClipSpan(1, 10.0, 14.0)
RED, MAGENTA = (255, 0, 0), (255, 0, 255)


def two_faces(center_y: float = 300.0) -> list[FaceBox]:
    """Return two 100 px faces centered at x 300 and 900 and center_y."""
    return [
        FaceBox(x=x - 50, y=center_y - 50, width=100.0, height=100.0, score=0.9)
        for x in (300.0, 900.0)
    ]


def near(color: Pixels, expected: tuple[int, int, int]) -> bool:
    """Return True if each channel of color is within 40 of expected."""
    return bool(np.all(np.abs(color.astype(int) - expected) <= 40))


@pytest.fixture(scope="module")
def gradient(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A lossless 30 fps, 80 s video, 1280x8, whose pixels in column X have
    red X // 256 and green X % 256: a crop's first pixel tells its x."""
    path = tmp_path_factory.mktemp("gradient") / "gradient.mkv"
    source = (
        f"color=size={GRADIENT_WIDTH}x8:rate=30:duration=80,format=gbrp,"
        "geq=r='trunc(X/256)':g='mod(X,256)':b=0"
    )
    run_ffmpeg(["-f", "lavfi", "-i", source, "-c:v", "ffv1", path])
    return path


@pytest.fixture(scope="module")
def rendered(
    sample_mp4: Path,
    tmp_path_factory: pytest.TempPathFactory,
    render_settings: RenderSettings,
) -> dict[Layout, tuple[Path, CropPlan]]:
    """The fixture's CLIP, with two faces in the frame, rendered at 9:16 in
    each layout, and its crop plan."""
    faces = [two_faces() for _ in range(40)]
    plan = plan_crop(CLIP, "9:16", (1280, 720), faces, [])
    out = tmp_path_factory.mktemp("layouts")
    layouts: tuple[Layout, ...] = ("fill", "fit", "split")
    return {
        layout: (
            render_clip(
                sample_mp4,
                out / f"{layout}.mp4",
                CLIP.start,
                CLIP.end,
                plan,
                layout,
                render_settings,
            ),
            plan,
        )
        for layout in layouts
    }


def test_window_x_moves_linearly_between_keyframes() -> None:
    assert window_x([10.0], [100], 10.0) == "100"
    assert window_x([10.0, 10.2, 10.4], [100, 100, 100], 10.0) == "100"
    assert (
        window_x([10.0, 10.2, 10.4], [100, 120, 90], 10.1)
        == "(100)+((+20*clip((t+0.100)/0.200,0,1))+(-30*clip((t-0.100)/0.200,0,1)))"
    )
    assert window_x([], [], 0.0) == "(iw-ow)/2"


def test_window_x_nests_a_long_sum_as_a_balanced_tree() -> None:
    xs = [k % 2 * 10 for k in range(1000)]

    expression = window_x([k / 5 for k in range(1000)], xs, 0.0)

    depth = deepest = 0
    for char in expression:
        depth += {"(": 1, ")": -1}.get(char, 0)
        deepest = max(deepest, depth)
    # 1000 terms as halves of halves: log2(1000) < 10 levels, and the 3
    # parentheses of a term; a flat sum would nest 999 deep for ffmpeg.
    assert deepest <= 13


def test_the_crop_follows_the_keyframes_at_every_frame(gradient: Path) -> None:
    # 300 keyframes (60 s) of a random walk, from 0.3 s before the clip.
    rng = np.random.default_rng(23)
    steps = rng.integers(-40, 41, 300)
    xs = [int(x) - int(x) % 2 for x in np.clip(438 + np.cumsum(steps), 0, 876)]
    times = [round(9.7 + k * 0.2, 3) for k in range(300)]
    keyframes = [
        CropKeyframe(t=t, x=x, faces=[]) for t, x in zip(times, xs, strict=True)
    ]
    window = CropWindow(width=404, height=8, y=0, xs=xs)
    plan = CropPlan(
        clip_id=1,
        start=10.0,
        end=69.0,
        aspect="9:16",
        width=404,
        height=8,
        y=0,
        keyframes=keyframes,
        layout="fill",
        split=(window, window),
    )

    result = run_ffmpeg(
        ["-ss", "10.000", "-i", gradient, "-t", "59.000", "-filter_complex"]
        + [f"[0:V:0]fps=30,{crop_window(plan, None, 10.0)}[v]", "-map", "[v]"]
        + ["-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    )

    frames = np.frombuffer(result.stdout, np.uint8).reshape(-1, 8, 404, 3)
    got = frames[:, 0, 0, 0].astype(int) * 256 + frames[:, 0, 0, 1]
    expected = np.interp(10.0 + np.arange(len(frames)) / 30, times, xs)
    assert len(frames) == 59 * 30
    assert np.abs(got - expected).max() <= 1


@pytest.mark.parametrize("layout", ["fill", "fit", "split"])
def test_each_layout_renders_the_clip_at_1080x1920(
    rendered: dict[Layout, tuple[Path, CropPlan]], layout: Layout
) -> None:
    video, _ = rendered[layout]

    info = probe_media(video)

    assert (info.width, info.height, info.fps) == (1080, 1920, 30)
    assert (info.video_codec, info.pix_fmt, info.audio_codec) == (
        "h264",
        "yuv420p",
        "aac",
    )
    assert info.duration == pytest.approx(4.0, abs=0.2)


def test_fit_shows_the_whole_frame_over_a_blurred_copy(
    rendered: dict[Layout, tuple[Path, CropPlan]],
) -> None:
    video, _ = rendered["fit"]

    frame = frame_at(video, 1.0)

    # The 1280x720 frame fits as 1080x608, 656 px from the top: its red and
    # cyan bars, at its left and right edges, are both in the middle row.
    middle = frame[656 + 91]
    assert near(middle[40], RED) and near(middle[1040], (0, 255, 255))
    # Above and below it, the copy scaled to fill is blurred: the edge of its
    # yellow and blue bars, sharp in the middle row, spreads over many pixels.
    top_row, bottom_row = frame[100], frame[1820]
    assert np.abs(np.diff(middle.astype(int), axis=0)).max() > 60
    for row in (top_row, bottom_row):
        assert np.abs(np.diff(row.astype(int), axis=0)).max() < 20
        assert near(row[100], (255, 255, 0)) and near(row[980], (0, 0, 255))


def test_split_stacks_the_windows_of_the_left_and_the_right_face(
    rendered: dict[Layout, tuple[Path, CropPlan]], sample_mp4: Path
) -> None:
    video, plan = rendered["split"]
    top, bottom = plan.split

    frame = frame_at(video, 1.0)

    # The top half shows the window on the face at x 300, the bottom half the
    # one on the face at x 900: 640x568 windows, 1080x960 in the output.
    assert (top.xs[5], bottom.xs[5], top.height) == (0, 580, 568)
    source = frame_at(sample_mp4, CLIP.start + 1.0)
    for window, half in ((top, frame[:960]), (bottom, frame[960:])):
        for u, v in ((0.25, 0.1), (0.5, 0.1), (0.85, 0.1)):
            x = window.xs[5] + round(u * window.width)
            y = window.y + round(v * window.height)
            expected = tuple(int(c) for c in source[y, x])
            assert near(half[round(v * 960), round(u * 1080)], expected)
    assert near(frame[96, 108], RED) and near(frame[960 + 96, 540], MAGENTA)


def still_plan(x: int) -> CropPlan:
    """A 404x8 fill window at x that stays there, in a 1280 px wide frame."""
    keyframes = [CropKeyframe(t=t, x=x, faces=[]) for t in (10.0, 12.0)]
    window = CropWindow(width=404, height=8, y=0, xs=[x, x])
    return CropPlan(
        clip_id=1,
        start=10.0,
        end=12.0,
        aspect="9:16",
        width=404,
        height=8,
        y=0,
        keyframes=keyframes,
        layout="fill",
        split=(window, window),
    )


def test_nudge_plan_shifts_the_fill_window_by_even_pixels() -> None:
    plan = still_plan(400)

    assert nudge_plan(plan, 0) is plan
    assert [k.x for k in nudge_plan(plan, 0.5).keyframes] == [602, 602]
    assert [k.x for k in nudge_plan(plan, -0.25).keyframes] == [300, 300]
    assert [k.x for k in nudge_plan(plan, -1).keyframes] == [0, 0]
    assert nudge_plan(plan, 0.5).split == plan.split


def first_pixel_x(gradient: Path, plan: CropPlan) -> int:
    """Render 1 s of gradient through plan's fill window; return the x of
    the source column that is the window's first pixel."""
    result = run_ffmpeg(
        ["-ss", "10.000", "-i", gradient, "-t", "1.000", "-filter_complex"]
        + [f"[0:V:0]fps=30,{crop_window(plan, None, 10.0)}[v]", "-map", "[v]"]
        + ["-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    )
    frames = np.frombuffer(result.stdout, np.uint8).reshape(-1, 8, 404, 3)
    return int(frames[0, 0, 0, 0]) * 256 + int(frames[0, 0, 0, 1])


def test_a_nudged_window_renders_shifted_and_stays_inside_the_frame(
    gradient: Path,
) -> None:
    plan = still_plan(400)

    assert first_pixel_x(gradient, nudge_plan(plan, 0.5)) == 602
    assert first_pixel_x(gradient, nudge_plan(plan, -0.25)) == 300
    # The frame is 1280 wide: the window's left edge stops at 876.
    assert first_pixel_x(gradient, nudge_plan(still_plan(700), 1)) == 876
    assert first_pixel_x(gradient, nudge_plan(plan, -1)) == 0
