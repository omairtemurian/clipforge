"""Tests of the camera motion of reframe's windows (pipeline/camera_motion,
steering: calmer auto-track): the pan caps, eased moves without a jump in
speed, the hold between moves, the catch-up when the subject leaves the
window, and fast, which is the path from before the setting."""

import pytest
from clipforge.models import CameraMotion
from clipforge.pipeline.camera_motion import (
    CALM,
    FAST,
    MOTIONS,
    STEP_CHANGE_EPSILON,
    Motion,
    move_samples,
    smoothstep,
)
from clipforge.pipeline.faces import SAMPLE_FPS
from clipforge.pipeline.smoothing import dead_zone, limit_speed, zero_lag
from clipforge.pipeline.tracking import follow, shots

WIDTH = 1000
# A 9:16 window of a 16:9 frame, in pixels of WIDTH.
CROP = 316
JUMP = [300.0] * 10 + [700.0] * 60


def old_follow(
    targets: list[float], resets: list[bool], frame_width: int
) -> list[float]:
    """tracking.follow from before the camera motion setting: smoothed,
    held in a dead-zone of 0.08 and limited to 0.25 frame widths a second."""
    centers: list[float] = []
    for shot in shots(resets):
        smooth = dead_zone(zero_lag([targets[k] for k in shot]), 0.08 * frame_width)
        centers.extend(limit_speed(smooth, 0.25 * frame_width / SAMPLE_FPS))
    return centers


def path(targets: list[float], motion: Motion, crop: int | None = None) -> list[float]:
    """The window centers that follow targets in one shot with motion."""
    return follow(targets, [True] + [False] * (len(targets) - 1), WIDTH, motion, crop)


def steps(centers: list[float]) -> list[float]:
    """How far the window moves from each sample to the next."""
    return [b - a for a, b in zip(centers, centers[1:], strict=False)]


def step_changes(centers: list[float]) -> list[float]:
    """How much each step differs from the one before it."""
    moves = steps(centers)
    return [abs(b - a) for a, b in zip(moves, moves[1:], strict=False)]


def runs(centers: list[float]) -> list[tuple[bool, int]]:
    """The (moving, steps) runs of the path: still and moving stretches."""
    found: list[tuple[bool, int]] = []
    for step in steps(centers):
        moving = abs(step) > 1e-9
        if found and found[-1][0] == moving:
            found[-1] = (moving, found[-1][1] + 1)
        else:
            found.append((moving, 1))
    return found


def test_the_camera_motions_table() -> None:
    assert MOTIONS == {
        "calm": Motion(dead_zone=0.12, max_pan=0.12, hold_s=1.0, eased=True),
        "normal": Motion(dead_zone=0.10, max_pan=0.18, hold_s=0.6, eased=True),
        "fast": Motion(dead_zone=0.08, max_pan=0.25, hold_s=0.0, eased=False),
    }


def test_a_move_lasts_at_least_0_6_s_and_its_peak_stays_within_the_pan() -> None:
    # 400 px at 120 px/s: 1.5 * 400 / 120 = 5 s; 10 px: the 0.6 s minimum.
    assert move_samples(400, WIDTH, 0.12) == 50
    assert move_samples(10, WIDTH, 0.12) == 6
    assert move_samples(400, WIDTH, 0.25) == 24
    assert (smoothstep(0.0), smoothstep(0.5), smoothstep(1.0)) == (0.0, 0.5, 1.0)


@pytest.mark.parametrize(
    ("name", "cap", "top", "moving"),
    [("calm", 12.0, 11.794, 50), ("normal", 18.0, 17.874, 33)],
)
def test_no_step_is_faster_than_the_pan_cap(
    name: CameraMotion, cap: float, top: float, moving: int
) -> None:
    centers = path(JUMP, MOTIONS[name])

    # The cap is max_pan of 1000 px a second, at 10 samples a second.
    assert cap == MOTIONS[name].max_pan * WIDTH / SAMPLE_FPS
    assert max(abs(step) for step in steps(centers)) == pytest.approx(top, abs=1e-3)
    assert top <= cap
    assert runs(centers)[:2] == [(False, 6), (True, moving)]
    assert centers[-1] == pytest.approx(700.0, abs=0.01)


def test_an_eased_move_has_no_jump_in_speed_at_its_start_or_end() -> None:
    calm = path(JUMP, CALM)
    fast = path(JUMP, FAST)

    moves = steps(calm)
    moving = [k for k, step in enumerate(moves) if abs(step) > 1e-9]
    # The first and last steps of the move are under half a pixel, and the
    # step never changes by more than 0.906 px from one sample to the next.
    assert moves[moving[0]] == pytest.approx(0.466, abs=1e-3)
    assert moves[moving[-1]] == pytest.approx(0.466, abs=1e-3)
    assert max(step_changes(calm)) == pytest.approx(0.906, abs=1e-3)
    assert max(step_changes(calm)) <= STEP_CHANGE_EPSILON * WIDTH
    # Fast starts at 12.5 px a sample at once, then 25.
    assert max(step_changes(fast)) == pytest.approx(12.5, abs=1e-3)
    assert max(step_changes(fast)) > STEP_CHANGE_EPSILON * WIDTH


def test_the_window_rests_for_the_hold_between_two_moves() -> None:
    # The subject comes back 1.2 s after it left: calm waits for its 1 s
    # hold (10 still steps), fast turns back after a single still step.
    back_and_forth = [300.0] * 10 + [450.0] * 12 + [300.0] * 40

    calm = runs(path(back_and_forth, CALM))
    fast = runs(path(back_and_forth, FAST))

    assert calm == [(False, 9), (True, 12), (False, 10), (True, 11), (False, 19)]
    assert fast[:4] == [(False, 6), (True, 5), (False, 1), (True, 3)]


def test_a_normal_window_rests_0_6_s_between_moves() -> None:
    restless = [300.0] * 10 + ([450.0] * 8 + [300.0] * 8) * 3 + [450.0] * 20

    found = runs(path(restless, MOTIONS["normal"]))

    rests = [count for moving, count in found[1:-1] if not moving]
    assert rests == [19, 10, 6]


def test_a_subject_leaving_the_window_is_caught_up_faster_but_eased() -> None:
    calm = path(JUMP, CALM, CROP)

    # 400 px is too far for a calm 5 s move (the subject is out of the
    # 316 px window): the move takes 2.4 s, up to 25 px a sample.
    assert runs(calm)[:2] == [(False, 6), (True, 24)]
    assert max(abs(step) for step in steps(calm)) == pytest.approx(24.519, abs=1e-3)
    assert max(step_changes(calm)) == pytest.approx(3.755, abs=1e-3)


def test_a_subject_leaving_the_window_cuts_the_hold_short() -> None:
    # The subject jumps out of the window 0.5 s after the first move ended:
    # the window re-aims without waiting for the rest of its hold.
    leaving = [300.0] * 10 + [420.0] * 14 + [800.0] * 50

    found = runs(path(leaving, CALM, CROP))

    assert found == [(False, 9), (True, 8), (False, 5), (True, 22), (False, 29)]
    assert path(leaving, CALM, CROP)[-1] == pytest.approx(800.0, abs=0.2)


def test_a_scene_cut_still_resets_the_window_at_once() -> None:
    targets = [300.0] * 5 + [700.0] * 5
    cut = [True, False, False, False, False, True, False, False, False, False]

    assert follow(targets, cut, WIDTH) == [300.0] * 5 + [700.0] * 5


@pytest.mark.parametrize(
    "targets",
    [
        JUMP,
        [300.0 + 4 * k for k in range(80)],
        [500.0, 510.0, 640.0, 630.0, 200.0, 220.0, 900.0, 880.0, 870.0] * 7,
    ],
)
def test_fast_is_the_path_from_before_the_setting(targets: list[float]) -> None:
    resets = [k % 25 == 0 for k in range(len(targets))]

    assert follow(targets, resets, WIDTH, FAST) == old_follow(targets, resets, WIDTH)
