"""Tests of moving subject tracking (pipeline/object_tracking, TASK-81) on
a synthetic video: a square that moves right at 120 px/s through 640x360."""

import logging
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
import pytest
from clipforge.config import Settings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import CropPlan, FaceBox, SignalEvent, SignalList, SourceMeta
from clipforge.pipeline.click_track import opencv_tracker
from clipforge.pipeline.faces import Frame, sample_times
from clipforge.pipeline.object_tracking import (
    MakeTracker,
    add_objects,
    coverage,
    moving_boxes,
    track_shot,
)
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.reframe_run import reframe_clips
from clipforge.pipeline.step import META, SIGNALS, SOURCE, write_json
from moving_square import HEIGHT, SIDE, TOP, WIDTH, make_moving_square, square_x

SIZE = (WIDTH, HEIGHT)
TIMES = sample_times(0.0, 4.0)


@pytest.fixture(scope="module")
def square(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The 4 s moving square video (tests/moving_square)."""
    return make_moving_square(tmp_path_factory.mktemp("objects") / "square.mp4")


class StuckTracker:
    """A tracker that always reports the top-left corner of the frame."""

    def init(self, image: Frame, box: tuple[int, int, int, int]) -> None:
        """Ignore the seed."""

    def update(self, image: Frame) -> tuple[bool, Sequence[float]]:
        """Return a box in the empty top-left corner."""
        return True, (0.0, 0.0, 20.0, 20.0)


def center(box: FaceBox) -> float:
    """Return box's center x in frame widths."""
    return (box.x + box.width / 2) / WIDTH


def crop_error(plan: CropPlan) -> float:
    """Return the largest distance, in frame widths, between the plan's crop
    center and the nearest center to the square that keeps the crop inside
    the frame."""
    half = plan.width / 2
    errors = []
    for keyframe in plan.keyframes:
        target = min(WIDTH - half, max(half, square_x(keyframe.t) * WIDTH))
        errors.append(abs(keyframe.x + half - target) / WIDTH)
    return max(errors)


def objects(faces: Sequence[Sequence[FaceBox]]) -> list[FaceBox]:
    """Return the only box of each sample that has one."""
    return [found[0] for found in faces if found]


def test_this_opencv_build_has_the_csrt_tracker() -> None:
    assert isinstance(opencv_tracker(), cv2.TrackerCSRT)


@pytest.mark.parametrize("make", [opencv_tracker, lambda: None], ids=["csrt", "none"])
def test_the_moving_square_is_tracked_in_a_shot_without_faces(
    square: Path, make: MakeTracker
) -> None:
    resets = [k == 0 for k in range(len(TIMES))]

    faces = add_objects(square, SIZE, TIMES, resets, [[]] * len(TIMES), make)

    found = objects(faces)
    assert len(found) >= 0.9 * len(TIMES)
    for t, sample in zip(TIMES, faces, strict=True):
        for box in sample:
            assert box.kind == "object" and box.score > 0.5
            assert center(box) == pytest.approx(square_x(t), abs=0.03)
            assert box.y + box.height / 2 == pytest.approx(TOP + SIDE / 2, abs=10)
            assert SIDE * 0.7 <= box.width <= SIDE * 1.4


@pytest.mark.parametrize("aspect", ["9:16", "1:1", "4:5"])
def test_the_crop_center_stays_within_a_tenth_of_the_width_of_the_square(
    square: Path, aspect: str
) -> None:
    resets = [k == 0 for k in range(len(TIMES))]
    faces = add_objects(square, SIZE, TIMES, resets, [[]] * len(TIMES))

    plan = plan_crop(
        ClipSpan(1, 0.0, 4.0), aspect, SIZE, faces, [], camera_motion="fast"
    )

    assert plan.layout == "fill" and plan.width < WIDTH
    assert crop_error(plan) < 0.1
    assert all(keyframe.faces[0].subject for keyframe in plan.keyframes)
    assert plan.keyframes[-1].x - plan.keyframes[0].x > 0.8 * (WIDTH - plan.width)


@pytest.mark.parametrize("aspect", ["9:16", "1:1", "4:5"])
def test_a_calm_crop_lags_the_square_but_keeps_it_in_the_window(
    square: Path, aspect: str
) -> None:
    resets = [k == 0 for k in range(len(TIMES))]
    faces = add_objects(square, SIZE, TIMES, resets, [[]] * len(TIMES))

    plan = plan_crop(ClipSpan(1, 0.0, 4.0), aspect, SIZE, faces, [])

    # The square (120 px/s, 0.19 frame widths a second) is faster than a
    # calm pan; the catch-up keeps its center inside the window.
    assert plan.camera_motion == "calm"
    assert crop_error(plan) < plan.width / 2 / WIDTH


def test_shots_with_faces_are_left_as_they_are(square: Path) -> None:
    face = FaceBox(x=100, y=100, width=50, height=50, score=0.9)
    faces = [[face] if k < 20 else [] for k in range(len(TIMES))]
    resets = [k in (0, 20) for k in range(len(TIMES))]

    result = add_objects(square, SIZE, TIMES, resets, faces)

    assert result[:20] == faces[:20]
    later = objects(result[20:])
    assert len(later) >= 18 and all(box.kind == "object" for box in later)


def test_a_still_video_has_no_moving_subject(tmp_path: Path) -> None:
    still = tmp_path / "still.mp4"
    run_ffmpeg(
        ["-f", "lavfi", "-i", "color=c=0x303030:s=640x360:d=2:r=25"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", still]
    )
    times = sample_times(0.0, 2.0)

    assert track_shot(still, SIZE, times) == [None] * len(times)


def test_a_short_shot_is_not_tracked(square: Path) -> None:
    assert track_shot(square, SIZE, TIMES[:4]) == [None] * 4


def test_a_tracker_stuck_on_the_background_loses_the_square(square: Path) -> None:
    boxes = track_shot(square, SIZE, TIMES, StuckTracker)

    kept = [k for k, box in enumerate(boxes) if box is not None]
    # Only the seed, the sample where the square is largest, is kept.
    assert len(kept) == 1


def test_moving_boxes_skips_tiny_and_frame_wide_changes() -> None:
    still = np.full((180, 320), 48, np.uint8)
    frame = np.full((180, 320, 3), 48, np.uint8)
    frame[50:80, 100:130] = 255
    frame[10:12, 10:12] = 255

    # The 5x5 blur spreads the 30 px square by a pixel on each side.
    assert moving_boxes(frame, still) == [(99.0, 49.0, 32.0, 32.0)]
    assert moving_boxes(np.full((180, 320, 3), 200, np.uint8), still) == []


def test_coverage_is_the_largest_share_one_moving_box_covers() -> None:
    box = (0.0, 0.0, 10.0, 10.0)

    assert coverage(box, [(5.0, 0.0, 10.0, 10.0), (0.0, 0.0, 10.0, 2.0)]) == 0.5
    assert coverage(box, [(-5.0, -5.0, 30.0, 30.0)]) == 1.0
    assert coverage(box, [(20.0, 20.0, 5.0, 5.0)]) == 0.0


@pytest.mark.slow
def test_reframe_follows_the_square_where_no_face_is_seen(
    square: Path, face_cfg: Settings, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    (tmp_path / SOURCE).write_bytes(square.read_bytes())
    meta = SourceMeta(
        title="square",
        duration=4.0,
        width=WIDTH,
        height=HEIGHT,
        fps=25.0,
        timeframe_start=0.0,
        timeframe_end=4.0,
    )
    write_json(tmp_path / META, meta)
    write_json(tmp_path / SIGNALS, SignalList([]))

    (path,) = reframe_clips(
        tmp_path, [ClipSpan(1, 0.0, 4.0)], "9:16", cfg=face_cfg, camera_motion="fast"
    )

    plan = CropPlan.model_validate_json(path.read_bytes())
    assert crop_error(plan) < 0.1
    seen = sum(bool(keyframe.faces) for keyframe in plan.keyframes)
    assert seen >= 36
    assert any(
        f"faces in 0 of 40 frames, objects in {seen}, crop 202x360" in message
        for message in caplog.messages
    )


def test_a_scene_cut_event_starts_a_new_tracked_shot(square: Path) -> None:
    cut = SignalEvent(kind="scene_cut", start=2.0, end=2.0, intensity=1.0)
    resets = [k in (0, 20) for k in range(len(TIMES))]

    faces = add_objects(square, SIZE, TIMES, resets, [[]] * len(TIMES))
    plan = plan_crop(ClipSpan(1, 0.0, 4.0), "9:16", SIZE, faces, [cut.start])

    assert crop_error(plan) < 0.1
