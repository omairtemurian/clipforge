"""Tests of reframe's subject tracking (pipeline/tracking) on synthetic face
tracks: the subject, gaps without faces, the smoothing, the speed limit and
the resets at scene cuts."""

import pytest
from clipforge.models import Aspect, FaceBox
from clipforge.pipeline.camera_motion import FAST
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import SIZES, center_crop
from clipforge.pipeline.tracking import (
    bridge_switches,
    fill_gaps,
    follow,
    reset_flags,
    subject_centers,
    subject_tracks,
    track_subject,
)

ONE_SHOT = [True] + [False] * 5


def face(
    center_x: float,
    size: float = 100.0,
    *,
    subject: bool = False,
    track: int | None = None,
) -> FaceBox:
    """Return a square face of the given size centered at center_x."""
    return FaceBox(
        x=center_x - size / 2,
        y=300.0,
        width=size,
        height=size,
        score=0.9,
        track=track,
        subject=subject,
    )


def test_the_window_follows_the_subject_as_even_crop_x_inside_the_frame() -> None:
    faces = [[face(center)] for center in (500, 520, 530, 600, 600, 600)]

    xs = track_subject(faces, ONE_SHOT, 1000, 100, FAST)

    # Zero lag: the window starts toward 600 before the subject gets there,
    # holds while the smoothed path stays in the 80 px dead-zone and pans at
    # most 25 px (25% of 1000 px a second, 10 samples a second) a sample.
    assert xs == [474, 474, 474, 488, 512, 524]


def test_by_default_the_window_rests_then_eases_toward_the_subject() -> None:
    faces = [[face(center)] for center in (500, 520, 530, 600, 600, 600)]

    xs = track_subject(faces, ONE_SHOT, 1000, 100)

    # Calm: it rests in the 120 px dead-zone, then starts an eased move
    # (slowly at first) once the subject leaves the 100 px window.
    assert xs == [474, 474, 474, 474, 478, 490]


def test_a_scene_cut_resets_the_window_to_the_new_subject() -> None:
    targets = [300.0] * 5 + [700.0] * 5
    cut = [True, False, False, False, False, True, False, False, False, False]

    assert follow(targets, cut, 1000) == [300.0] * 5 + [700.0] * 5


def test_without_a_cut_the_window_pans_to_the_new_subject_at_the_speed_limit() -> None:
    path = follow([300.0] * 10 + [700.0] * 10, [True] + [False] * 19, 1000, FAST)

    assert path == pytest.approx(
        [312.576, 325.076, 337.576, 350.076, 362.576, 375.076, 400.076, 425.0]
        + [450.0, 475.0, 500.0, 525.0, 550.0, 575.0, 587.5, 600.0]
        + [621.465, 646.465, 658.965, 671.465],
        abs=1e-3,
    )
    assert max(abs(b - a) for a, b in zip(path, path[1:], strict=False)) <= 25


def test_reset_flags_mark_the_first_sample_and_the_first_one_after_each_cut() -> None:
    times = sample_times(10.0, 10.5)

    # Cuts before the clip, at a sample, between samples and after the clip.
    flags = reset_flags(times, [4.0, 10.2, 10.25, 11.5])

    assert times == [10.0, 10.1, 10.2, 10.3, 10.4]
    assert flags == [True, False, True, True, False]


def test_the_subject_is_the_marked_face() -> None:
    faces = [
        [face(900, 120), face(200, 80, subject=True)],
        [face(900, 120)],
        [face(300, subject=True)],
    ]

    assert subject_centers(faces) == [200.0, None, 300.0]


def test_without_marked_faces_the_subject_is_the_largest_face() -> None:
    faces = [[face(200, 80), face(900, 120), face(500, 100)], [], [face(300)]]

    assert subject_centers(faces) == [900.0, None, 300.0]


def test_a_new_subject_fills_the_gap_after_the_old_one_in_its_shot() -> None:
    faces = [
        [face(300, subject=True, track=0)],
        [],
        [face(900, track=1)],
        [face(700, subject=True, track=2)],
        [],
        [face(800, subject=True, track=3)],
        [face(500, subject=True)],
    ]
    tracks = subject_tracks(faces)
    resets = [True, False, False, False, False, True, False]

    bridged = bridge_switches(subject_centers(faces), tracks, resets)

    assert tracks == [0, None, None, 2, None, 3, None]
    # Samples 1-2 head for track 2; sample 4 is the end of its shot (a cut
    # starts track 3), and a subject without a track is not a change.
    assert bridged == [300.0, 700.0, 700.0, 700.0, None, 800.0, 500.0]


def test_a_gap_shorter_than_a_second_holds_the_subject() -> None:
    centers = [300.0] + [None] * 9 + [700.0]

    targets = fill_gaps(centers, [True] + [False] * 10, 640.0)

    assert targets == [300.0] * 10 + [700.0]


def test_in_a_gap_of_a_second_or_more_the_window_moves_to_where_it_ends() -> None:
    centers = [300.0] + [None] * 10 + [410.0]

    targets = fill_gaps(centers, [True] + [False] * 11, 640.0)

    assert targets == pytest.approx([300.0 + 10.0 * k for k in range(12)])


def test_samples_before_the_first_face_of_a_shot_take_that_face() -> None:
    centers = [None, None, 400.0, None, None, 800.0, None]
    resets = [True, False, False, False, True, False, False]

    assert fill_gaps(centers, resets, 640.0) == [400.0] * 4 + [800.0] * 3


def test_a_shot_without_faces_holds_the_subject_of_the_shots_before_it() -> None:
    resets = [True, False, True, False]

    assert fill_gaps([400.0, None, None, None], resets, 640.0) == [400.0] * 4
    assert (
        fill_gaps([None, None, 900.0, None], resets, 640.0) == [640.0] * 2 + [900.0] * 2
    )


@pytest.mark.parametrize(
    ("frame_size", "aspect", "x"),
    [
        ((1280, 720), "9:16", 438),
        ((1920, 1080), "9:16", 656),
        ((1280, 720), "1:1", 280),
        ((1280, 720), "16:9", 0),
    ],
)
def test_a_clip_without_faces_is_center_cropped(
    frame_size: tuple[int, int], aspect: Aspect, x: int
) -> None:
    no_faces: list[list[FaceBox]] = [[] for _ in range(10)]

    plan = plan_crop(ClipSpan(3, 10.0, 11.0), aspect, frame_size, no_faces, [])

    crop = center_crop(*frame_size, *SIZES[aspect])
    assert [keyframe.x for keyframe in plan.keyframes] == [x] * 10
    assert (plan.width, plan.height, plan.y, x) == (crop.width, crop.height, 0, crop.x)


def test_the_window_stays_inside_the_frame() -> None:
    faces = [[face(30.0)], [face(30.0)], [face(1270.0)], [face(1270.0)]]

    xs = track_subject(faces, [True, False, True, False], 1280, 404)

    assert xs == [0, 0, 876, 876]


def test_plan_crop_marks_the_subject_and_gives_the_window_of_each_sample() -> None:
    faces = [[face(640.0)], [face(640.0)], [], [face(900.0)], [face(900.0)]]

    plan = plan_crop(ClipSpan(7, 10.0, 10.5), "9:16", (1280, 720), faces, [10.3])

    assert (plan.clip_id, plan.start, plan.end, plan.aspect) == (7, 10.0, 10.5, "9:16")
    assert (plan.width, plan.height, plan.y) == (404, 720, 0)
    keyframes = [(k.t, k.x, k.faces) for k in plan.keyframes]
    assert keyframes == [
        (10.0, 438, [face(640.0, subject=True, track=0)]),
        (10.1, 438, [face(640.0, subject=True, track=0)]),
        (10.2, 438, []),
        (10.3, 698, [face(900.0, subject=True, track=1)]),
        (10.4, 698, [face(900.0, subject=True, track=1)]),
    ]


@pytest.mark.parametrize(
    ("start", "end", "count"),
    [(0.5, 34.35, 339), (0.0, 2.0, 20), (0.1, 2.1, 20), (33.3, 34.35, 11), (1, 1.1, 1)],
)
def test_samples_are_taken_10_times_a_second(
    start: float, end: float, count: int
) -> None:
    times = sample_times(start, end)

    assert len(times) == count
    assert times[0] == start
    assert all(t < end for t in times)
    assert times == [round(start + k * 0.1, 3) for k in range(count)]
