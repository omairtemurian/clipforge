"""Tests of the split layout (SPEC 6.8) on synthetic faces: when reframe
picks it, and the two windows that follow the left and the right face."""

import pytest
from clipforge.models import Aspect, FaceBox, Layout
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop, split_windows, wants_split
from clipforge.pipeline.tracking import face_pairs, reset_flags


def face(center_x: float, size: float = 100.0, center_y: float = 300.0) -> FaceBox:
    """Return a square face of the given size centered at (center_x, center_y)."""
    return FaceBox(
        x=center_x - size / 2,
        y=center_y - size / 2,
        width=size,
        height=size,
        score=0.9,
    )


def samples(with_two: int, total: int) -> list[list[FaceBox]]:
    """Return the faces of total samples: two faces in with_two of them, one
    in the others."""
    two, one = [face(300.0), face(900.0)], [face(300.0)]
    return [two if k < with_two else one for k in range(total)]


@pytest.mark.parametrize(
    ("with_two", "total", "split"),
    [(59, 100, False), (60, 100, False), (61, 100, True), (3, 5, False), (4, 5, True)],
)
def test_two_faces_must_persist_in_more_than_60_percent_of_the_samples(
    with_two: int, total: int, split: bool
) -> None:
    assert wants_split(samples(with_two, total)) is split


def test_more_than_two_faces_count_and_a_clip_without_samples_does_not_split() -> None:
    three = [face(100.0), face(500.0), face(900.0)]

    assert wants_split([three, three, []]) is True
    assert wants_split([]) is False


@pytest.mark.parametrize(
    ("with_two", "aspect", "layout"),
    [
        (61, "9:16", "split"),
        (61, "1:1", "split"),
        (59, "9:16", "fill"),
        # The 16:9 window is the whole 16:9 frame: both faces are in it.
        (100, "16:9", "fill"),
    ],
)
def test_reframe_picks_split_when_two_faces_persist_and_the_window_is_narrower(
    with_two: int, aspect: Aspect, layout: Layout
) -> None:
    # 20 s at 10 samples a second.
    faces = samples(2 * with_two, 200)

    plan = plan_crop(ClipSpan(1, 0.0, 20.0), aspect, (1280, 720), faces, [])

    assert plan.layout == layout


def test_the_pair_is_the_two_largest_faces_left_first() -> None:
    small, left, right = face(640.0, 50.0), face(300.0, 120.0), face(900.0)

    pairs = face_pairs([[right, small, left], [left], []])

    assert pairs == [(left, right), None, None]


@pytest.mark.parametrize(
    ("aspect", "size"),
    [("9:16", (640, 568)), ("1:1", (640, 320)), ("16:9", (640, 180))],
)
def test_split_windows_have_the_shape_of_half_the_output_frame(
    aspect: Aspect, size: tuple[int, int]
) -> None:
    no_faces: list[list[FaceBox]] = [[], [], []]

    top, bottom = split_windows(no_faces, [True, False, False], (1280, 720), aspect)

    # The largest windows of that shape in half of the 1280x720 frame; without
    # faces they show its left and right halves, centered vertically.
    assert (top.width, top.height) == (bottom.width, bottom.height) == size
    assert (top.xs, bottom.xs) == ([0] * 3, [640] * 3)
    assert top.y == bottom.y == (720 - size[1]) // 2


def test_the_top_window_follows_the_left_face_and_the_bottom_one_the_right() -> None:
    times = sample_times(0.0, 1.0)
    pair = [face(900.0, center_y=250.0), face(500.0, center_y=400.0)]
    # Samples with fewer than two faces hold the windows of the pair.
    faces = [pair] * 4 + [[face(640.0)], [face(640.0)], [], []] + [pair] * 2

    top, bottom = split_windows(faces, reset_flags(times, []), (1280, 720), "9:16")

    # 640x568 windows centered on the faces: 500 - 320 and 900 - 320; their
    # tops center the faces' heights, 400 - 284, and 250 - 284 inside the frame.
    assert (top.xs, bottom.xs) == ([180] * 10, [580] * 10)
    assert (top.y, bottom.y) == (116, 0)


def test_split_windows_stay_inside_the_frame_and_jump_at_a_scene_cut() -> None:
    times = sample_times(0.0, 1.0)
    first, second = [face(40.0), face(700.0)], [face(400.0), face(1250.0)]
    faces = [first] * 4 + [second] * 6

    top, bottom = split_windows(faces, reset_flags(times, [0.4]), (1280, 720), "1:1")

    # Centers near an edge are aimed at as if they were half a window in.
    assert top.xs == [0] * 4 + [80] * 6
    assert bottom.xs == [380] * 4 + [640] * 6


def test_plan_crop_keeps_one_split_x_per_keyframe() -> None:
    faces = samples(10, 10)

    plan = plan_crop(ClipSpan(9, 30.0, 31.0), "9:16", (1280, 720), faces, [])

    top, bottom = plan.split
    assert len(plan.keyframes) == len(top.xs) == len(bottom.xs) == 10
    assert (plan.layout, top.xs[0], bottom.xs[0]) == ("split", 0, 580)
