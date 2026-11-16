"""Smoothing of a crop window's path over one shot (TASK-22).

The whole clip is known before it is rendered, so the window's path is
smoothed offline, without lag:

1. zero_lag: an exponential moving average run forward and then backward
   (a zero-phase filter, like scipy.signal.filtfilt, with PAD copies of
   the first and last value on each side so its ends are not pulled
   toward the other end), so the window is not late behind the subject;
2. dead_zone: the window aims at the smoothed center again only when that
   is more than half of the dead-zone away from where it aims, so small
   moves of the subject do not move the window;
3. limit_speed: the window moves at most max_step a sample; a move starts
   before and ends after the jump in its aim by the same time (the mean of
   the path limited forward in time and backward), so it is centered on it.
"""

from collections.abc import Sequence

# The weight of a sample in each pass of the zero-lag average (10 samples
# a second: each pass has a time constant of ~0.23 s).
ALPHA = 0.3
# Copies of each end value the zero-lag average runs over first: 0.7^20 <
# 0.001 of a jump at an end is left.
PAD = 20


def zero_lag(values: Sequence[float], alpha: float = ALPHA) -> list[float]:
    """Return values smoothed by a forward then a backward exponential
    moving average of weight alpha, over values padded with PAD copies of
    the first and the last value."""
    if not values:
        return []
    padded = [values[0]] * PAD + list(values) + [values[-1]] * PAD
    forward = _average(padded, alpha)
    return _average(forward[::-1], alpha)[::-1][PAD:-PAD]


def dead_zone(values: Sequence[float], width: float) -> list[float]:
    """Return the aim at each of values: the first value, then each value
    that is more than width / 2 from the aim before it."""
    aims: list[float] = []
    for value in values:
        if not aims or abs(value - aims[-1]) > width / 2:
            aims.append(value)
        else:
            aims.append(aims[-1])
    return aims


def limit_speed(values: Sequence[float], max_step: float) -> list[float]:
    """Return values moved at most max_step from one to the next: the mean
    of values followed forward in time and backward at that speed."""
    forward = _follow(values, max_step)
    backward = _follow(values[::-1], max_step)[::-1]
    return [(a + b) / 2 for a, b in zip(forward, backward, strict=True)]


def _average(values: Sequence[float], alpha: float) -> list[float]:
    """Return the exponential moving average of values, from the first."""
    result: list[float] = []
    for value in values:
        result.append(
            value if not result else result[-1] + alpha * (value - result[-1])
        )
    return result


def _follow(values: Sequence[float], max_step: float) -> list[float]:
    """Return a path that starts at the first of values and moves toward
    each next one by at most max_step."""
    result: list[float] = []
    for value in values:
        if not result:
            result.append(value)
            continue
        step = min(max(value - result[-1], -max_step), max_step)
        result.append(result[-1] + step)
    return result
