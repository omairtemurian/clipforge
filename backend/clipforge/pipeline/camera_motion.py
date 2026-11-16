"""Camera motion of reframe's crop windows (steering: calmer auto-track):
how a window moves from one aim to the next within a shot.

The project's "Camera motion" setting picks one of MOTIONS:

- fast (the motion before this setting): the zero-lag path held in a
  dead-zone and limited to max_pan of the frame width a second
  (pipeline/smoothing), so a move starts and stops at full speed;
- calm (the default) and normal: the window rests at its aim until the
  smoothed subject (smoothing.zero_lag) is more than half the dead-zone
  away and at least hold_s has passed since its last move ended. It then
  re-aims at where the subject is when the move ends (the path is known
  before the render) in one eased move (smoothstep, so its speed
  rises from and falls to 0, with no jump at either end) that lasts
  max(MIN_MOVE_S, PEAK * distance / max_pan) seconds: PEAK is the
  smoothstep's top speed over its mean speed, so the fastest step of the
  move stays within max_pan.

Catch-up: if the subject would leave the crop window during a move (its
center farther than EXIT_SHARE of the window's width from the window's
center), the move is faster, up to CATCH_UP_PAN (fast's max_pan), still
eased; if it leaves the window while the window rests, the window re-aims
at once, without waiting for the hold. Scene cuts start a new shot, where
the window jumps (pipeline/tracking).
"""

import math
from collections.abc import Sequence
from typing import NamedTuple

from clipforge.models import CameraMotion
from clipforge.pipeline.faces import SAMPLE_FPS
from clipforge.pipeline.smoothing import dead_zone, limit_speed, zero_lag


class Motion(NamedTuple):
    """How a window moves: dead_zone is the width (in frame widths) in
    which it holds still, max_pan its fastest pan (frame widths a second),
    hold_s the least rest (seconds) between two moves and eased whether
    its moves are eased (False: the fast path of smoothing.limit_speed)."""

    dead_zone: float
    max_pan: float
    hold_s: float
    eased: bool


MOTIONS: dict[CameraMotion, Motion] = {
    "calm": Motion(dead_zone=0.12, max_pan=0.12, hold_s=1.0, eased=True),
    "normal": Motion(dead_zone=0.10, max_pan=0.18, hold_s=0.6, eased=True),
    "fast": Motion(dead_zone=0.08, max_pan=0.25, hold_s=0.0, eased=False),
}
CALM = MOTIONS["calm"]
FAST = MOTIONS["fast"]

# The fastest pan of a catch-up move, in frame widths a second.
CATCH_UP_PAN = 0.25
# The shortest eased move, in seconds.
MIN_MOVE_S = 0.6
# The smoothstep's top speed (at its middle) over its mean speed.
PEAK = 1.5
# A subject whose center is farther than this share of the window's width
# from the window's center is leaving the window.
EXIT_SHARE = 0.4
# The most the step of an eased path changes from one sample to the next,
# in frame widths (fast's moves change it by up to 0.025 at once).
STEP_CHANGE_EPSILON = 0.012


def smoothstep(share: float) -> float:
    """Return the eased share (3u^2 - 2u^3) of a move share of the way."""
    return share * share * (3 - 2 * share)


def move_samples(distance: float, frame_width: int, pan: float) -> int:
    """Return how many samples an eased move of distance pixels lasts:
    max(MIN_MOVE_S, PEAK * distance / pan frame widths a second)."""
    seconds = max(MIN_MOVE_S, PEAK * distance / (pan * frame_width))
    return max(1, math.ceil(seconds * SAMPLE_FPS - 1e-9))


def shot_path(
    targets: Sequence[float],
    frame_width: int,
    motion: Motion = CALM,
    crop_width: int | None = None,
) -> list[float]:
    """Return the window center at each sample of one shot that follows
    targets with motion (module docstring) in a frame_width video; the
    catch-up applies only with crop_width, the window's width."""
    if not motion.eased:
        path = dead_zone(zero_lag(targets), motion.dead_zone * frame_width)
        return limit_speed(path, motion.max_pan * frame_width / SAMPLE_FPS)
    aims = zero_lag(targets)
    if not aims:
        return []
    hold = round(motion.hold_s * SAMPLE_FPS)
    path = [aims[0]]
    ready = 0
    k = 1
    while k < len(aims):
        here = path[-1]
        leaving = _leaves(aims[k], here, crop_width)
        far = abs(aims[k] - here) > motion.dead_zone * frame_width / 2
        if leaving or (far and k >= ready):
            move = _move(aims, k, here, frame_width, motion.max_pan, crop_width)
            path.extend(move[: len(aims) - k])
            k += len(move)
            ready = k + hold
        else:
            path.append(here)
            k += 1
    return path


def _move(
    aims: Sequence[float],
    first: int,
    start: float,
    frame_width: int,
    pan: float,
    crop_width: int | None,
) -> list[float]:
    """Return the eased move's window centers from sample first on, from
    start to where the subject (aims) is when the move ends (_eased), at
    pan; at the catch-up pan if the subject leaves the window at that pan."""
    move = _eased(aims, first, start, frame_width, pan)
    if any(
        _leaves(aims[first + i], center, crop_width)
        for i, center in enumerate(move)
        if first + i < len(aims)
    ):
        move = _eased(aims, first, start, frame_width, max(pan, CATCH_UP_PAN))
    return move


def _eased(
    aims: Sequence[float], first: int, start: float, frame_width: int, pan: float
) -> list[float]:
    """Return the samples from first on of a smoothstep move from start
    that ends where the subject (aims) is when it ends: the shortest move
    of count samples to aims[first + count - 1] that is not faster than
    pan; toward the shot's last aim if no move catches the subject."""
    end = aims[-1]
    count = move_samples(abs(end - start), frame_width, pan)
    for length in range(1, len(aims) - first + 1):
        later = aims[first + length - 1]
        if move_samples(abs(later - start), frame_width, pan) <= length:
            end, count = later, length
            break
    return [start + (end - start) * smoothstep(i / count) for i in range(1, count + 1)]


def _leaves(subject: float, center: float, crop_width: int | None) -> bool:
    """Return True if the subject's center is leaving a crop_width window
    centered at center (EXIT_SHARE); never without a crop_width."""
    return crop_width is not None and abs(subject - center) > EXIT_SHARE * crop_width
