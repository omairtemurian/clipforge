"""Tests of manual reframe keyframes (pipeline/keyframes): setting and
deleting them on a scene, the window between them, the crop expression
that ffmpeg evaluates at each frame, and a render that follows them."""

import re
from pathlib import Path

import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import CropPlan, CropPoint, FaceBox, SceneReframe
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.keyframes import (
    KeyframeError,
    NoKeyframe,
    delete_keyframe,
    scene_index,
    set_keyframe,
    window_at,
)
from clipforge.pipeline.layout_parts import crop_window, even
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.scene_framing import keyframed_plan
from clipforge.pipeline.scene_graph import ScenePart
from frames import frame_at

FRAME = (1280, 720)
CLIP = ClipSpan(1, 10.0, 14.0)
SIZE = (216, 384)
RED, BLUE = (255, 0, 0), (0, 0, 255)
# One line per frame of ffmpeg's crop filter at loglevel trace
# (libavfilter/vf_crop.c filter_frame).
CROP_LOG = re.compile(r"n:(\d+) t:([\d.]+) x:(\d+) y:(\d+)")


def point(t: float, x: float = 0.5, y: float = 0.5) -> CropPoint:
    """A crop keyframe at t seconds centered at (x, y)."""
    return CropPoint(t=t, x=x, y=y)


def scene(*points: CropPoint, **fields: object) -> SceneReframe:
    """A scene from 10 to 14 s with keyframes points and fields."""
    return SceneReframe.model_validate(
        {"start": 10.0, "end": 14.0, "crop_keyframes": points} | fields
    )


def planned() -> CropPlan:
    """The 9:16 plan of CLIP in a FRAME source with no faces."""
    no_faces: list[list[FaceBox]] = [[] for _ in sample_times(CLIP.start, CLIP.end)]
    return plan_crop(CLIP, "9:16", FRAME, no_faces, [])


def keyed_plan(*points: CropPoint) -> CropPlan:
    """The plan of a fixed half-size scene of CLIP at points."""
    keyed = scene(*points, mode="fixed", scale=0.5)
    return keyframed_plan(planned(), planned(), keyed, FRAME)


def test_setting_a_keyframe_replaces_near_ones_and_fixes_an_auto_scene() -> None:
    auto = scene(point(10.5), point(12.0, 0.2))

    keyed = set_keyframe(auto, point(12.05, 0.9, 0.1), scale=0.5)

    assert keyed.mode == "fixed"
    assert keyed.scale == 0.5
    assert keyed.crop_keyframes == [point(10.5), point(12.05, 0.9, 0.1)]
    added = set_keyframe(keyed, point(11.0, 0.3))
    assert [key.t for key in added.crop_keyframes] == [10.5, 11.0, 12.05]
    assert added.scale == 0.5
    tracked = set_keyframe(scene(mode="track"), point(9.0))
    assert tracked.mode == "track"
    assert tracked.crop_keyframes == [point(10.0)]
    assert set_keyframe(scene(), point(13.98765)).crop_keyframes[0].t == 13.988


def test_only_a_fill_scene_takes_keyframes() -> None:
    with pytest.raises(KeyframeError, match="fit layout"):
        set_keyframe(scene(layout="fit"), point(11.0))


def test_deleting_removes_the_nearest_keyframe_within_the_gap() -> None:
    keyed = scene(point(11.0), point(11.15), point(13.0), mode="fixed")

    assert [key.t for key in delete_keyframe(keyed, 11.1).crop_keyframes] == [
        11.0,
        13.0,
    ]
    with pytest.raises(NoKeyframe):
        delete_keyframe(keyed, 12.0)


def test_the_scene_at_a_time_is_the_later_one_on_an_edge() -> None:
    scenes = [
        SceneReframe(start=10.0, end=11.0),
        SceneReframe(start=11.0, end=12.5),
    ]

    assert scene_index(scenes, 10.0) == 0
    assert scene_index(scenes, 11.0) == 1
    assert scene_index(scenes, 12.5) == 1
    with pytest.raises(KeyframeError, match="not inside"):
        scene_index(scenes, 12.6)


def test_the_window_moves_linearly_between_keyframes_and_holds_outside() -> None:
    plan = keyed_plan(point(11.0, 0.25, 0.25), point(13.0, 0.75, 0.75))
    first, last = plan.keyframes
    assert first.y is not None and last.y is not None

    assert window_at(plan, 10.0, FRAME[0]) == (first.x, first.y)
    assert window_at(plan, 11.0, FRAME[0]) == (first.x, first.y)
    assert window_at(plan, 12.0, FRAME[0]) == (
        (first.x + last.x) / 2,
        (first.y + last.y) / 2,
    )
    assert window_at(plan, 12.5, FRAME[0])[0] == first.x + (last.x - first.x) * 0.75
    assert window_at(plan, 14.0, FRAME[0]) == (last.x, last.y)
    still = planned().model_copy(update={"keyframes": []})
    assert window_at(still, 12.0, FRAME[0]) == ((1280 - still.width) / 2, still.y)


def test_ffmpeg_evaluates_the_crop_expression_at_each_frame_as_expected() -> None:
    plan = keyed_plan(
        point(10.5, 0.2, 0.3), point(11.7, 0.8, 0.7), point(13.0, 0.5, 0.45)
    )
    source = "color=size=1280x720:rate=10:duration=4,format=yuv420p"

    result = run_ffmpeg(
        ["-f", "lavfi", "-i", source, "-vf", crop_window(plan, None, CLIP.start)]
        + ["-f", "null", "-"],
        loglevel="trace",
    )

    frames = CROP_LOG.findall(result.stderr.decode())
    assert len(frames) == 40
    xs, ys = set(), set()
    for _, t, x, y in frames:
        expected_x, expected_y = window_at(plan, CLIP.start + float(t), FRAME[0])
        # crop rounds to the nearest pixel (lrint), keeps the window inside
        # the frame, then rounds down to even pixels for 4:2:0 chroma.
        right, bottom = FRAME[0] - plan.width, FRAME[1] - plan.height
        assert int(x) == even(min(max(round(expected_x), 0), right)), t
        assert int(y) == even(min(max(round(expected_y), 0), bottom)), t
        xs.add(int(x))
        ys.add(int(y))
    first = plan.keyframes[0]
    assert frames[0][2:] == (str(first.x), str(first.y))
    assert len(xs) > 20 and len(ys) > 20


@pytest.fixture(scope="module")
def halves(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 16 s 1280x720 video, red on the left half and blue on the right."""
    path = tmp_path_factory.mktemp("halves") / "halves.mp4"
    video = (
        "color=size=1280x720:rate=30:duration=16,format=gbrp,"
        "geq=r='255*lt(X,640)':g=0:b='255*gte(X,640)',format=yuv420p"
    )
    run_ffmpeg(
        ["-f", "lavfi", "-i", video, "-f", "lavfi", "-i"]
        + ["anullsrc=r=48000:cl=stereo", "-t", "16", "-c:v", "libx264"]
        + ["-c:a", "aac", "-shortest", path]
    )
    return path


def test_a_render_follows_the_keyframes_across_the_frame(
    halves: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    plan = keyed_plan(point(10.5, 0.0), point(13.5, 1.0))
    output = tmp_path / "keyed.mp4"

    render_clip(
        halves, output, CLIP.start, CLIP.end, planned(), "fill", render_settings,
        size=SIZE, scenes=[ScenePart(CLIP.start, CLIP.end, plan, "fill")],
    )  # fmt: skip

    info = probe_media(output)
    assert (info.width, info.height) == SIZE
    assert info.duration == pytest.approx(CLIP.end - CLIP.start, abs=0.1)
    middle = (SIZE[1] // 2, SIZE[0] // 2)
    assert near(frame_at(output, 0.2)[middle], RED)
    assert near(frame_at(output, 3.8)[middle], BLUE)
    # Halfway the window straddles the halves: red left, blue right.
    halfway = frame_at(output, 2.0)
    assert near(halfway[middle[0], 10], RED)
    assert near(halfway[middle[0], SIZE[0] - 10], BLUE)


def near(color: np.ndarray, expected: tuple[int, int, int]) -> bool:
    """Return True if each channel of color is within 40 of expected."""
    return bool(np.all(np.abs(color.astype(int) - expected) <= 40))
