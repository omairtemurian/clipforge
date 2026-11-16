"""Tests of the smoothing of a crop window's path (pipeline/smoothing): the
zero-lag average, the dead-zone and the centered speed limit."""

import pytest
from clipforge.pipeline.smoothing import dead_zone, limit_speed, zero_lag


def test_the_zero_lag_average_of_a_jump_is_centered_on_it() -> None:
    path = zero_lag([0.0] * 6 + [10.0] * 6)

    assert path == pytest.approx(
        [0.6921, 0.9886, 1.4124, 2.0176, 2.8824, 4.1176]
        + [5.8824, 7.1176, 7.9824, 8.5876, 9.0114, 9.3079],
        abs=1e-4,
    )
    # No lag: the path is as far below the jump as above it, around the
    # middle of the jump (between samples 5 and 6); the padding leaves less
    # than 0.001 of the jump at the ends.
    sums = [path[k] + path[11 - k] for k in range(6)]
    assert sums == pytest.approx([10.0] * 6, abs=1e-6)


def test_the_ends_of_the_zero_lag_average_are_not_pulled_to_the_other_end() -> None:
    path = zero_lag([0.0, 0.0, 0.0, 10.0, 10.0, 10.0])

    assert path == pytest.approx(
        [2.0176, 2.8824, 4.1176, 5.8824, 7.1176, 7.9824], abs=1e-4
    )
    assert zero_lag([5.0] * 3) == [5.0] * 3
    assert zero_lag([]) == []


def test_the_aim_moves_only_when_the_path_leaves_the_dead_zone() -> None:
    # An 80 px dead-zone: the aim holds while the path is within 40 px of it.
    aims = dead_zone([500.0, 520.0, 530.0, 545.0, 560.0, 520.0, 600.0], 80.0)

    assert aims == [500.0, 500.0, 500.0, 545.0, 545.0, 545.0, 600.0]


def test_a_jump_becomes_a_pan_at_the_speed_limit_centered_on_it() -> None:
    path = limit_speed([0.0] * 4 + [10.0] * 4, 2.5)

    # Forward the window would reach 10 at sample 7, backward it would
    # leave 0 at sample 0; their mean pans from both sides of the jump.
    assert path == [0.0, 1.25, 2.5, 3.75, 6.25, 7.5, 8.75, 10.0]
    assert max(abs(b - a) for a, b in zip(path, path[1:], strict=False)) <= 2.5


def test_the_speed_limit_keeps_a_path_that_is_slow_enough() -> None:
    assert limit_speed([0.0, 1.0, 2.0, 2.0, 1.0], 2.5) == [0.0, 1.0, 2.0, 2.0, 1.0]
