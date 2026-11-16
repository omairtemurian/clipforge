"""Zoom and shake of a video (SPEC-v3 4.3), from frame-to-frame affine
estimation.

For each pair of consecutive grey frames, up to MAX_CORNERS corners of the
first (`cv2.goodFeaturesToTrack`) are followed into the second
(`cv2.calcOpticalFlowPyrLK`), and `cv2.estimateAffinePartial2D` (RANSAC)
fits a similarity (scale, rotation, shift) to them. Lucas-Kanade loses most
corners on a big step such as a 23 % punch, so the second frame is warped
back by that rough fit and the corners are followed and fitted again; the
motion is the two fits combined. A pair with fewer than MIN_POINTS tracked
corners or, in the second pass, fewer than MIN_INLIER_SHARE inliers has no
motion (a cut, a flash, a flat frame). Its scale is how much bigger the
picture got (> 1 zooms in); its shift is where the frame center moved, in
frame widths. Coherent motion of most of the picture (a subject walking
at the camera) also reads as a zoom.

Zooms: frames whose log scale step is at least ZOOM_STEP form runs of one
direction (gaps of up to ZOOM_GAP frames bridged); a run that changes the
scale by at least ZOOM_MIN_CHANGE (log) is a zoom, a punch if it lasts at
most PUNCH_FRAMES frames, else a ramp. Shakes: frames whose shift is at
least SHAKE_STEP and turns back against the frame before or after (the
picture jolts to and fro, unlike a pan) form spans (gaps of up to SHAKE_GAP
frames bridged) of at least SHAKE_FRAMES such frames.
"""

import math
from collections.abc import Sequence
from typing import Literal

import cv2
import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field

MAX_CORNERS = 300
CORNER_QUALITY = 0.01
CORNER_DISTANCE = 7
MIN_POINTS = 12
MIN_INLIER_SHARE = 0.5
RANSAC_PIXELS = 1.0
ZOOM_STEP = 0.002
ZOOM_GAP = 1
ZOOM_MIN_CHANGE = 0.04
PUNCH_FRAMES = 5
SHAKE_STEP = 0.004
SHAKE_GAP = 2
SHAKE_FRAMES = 3
DECIMALS = 4

Grey = npt.NDArray[np.uint8]


class PairMotion(BaseModel):
    """The motion from one frame to the next: scale (> 1 zooms in) and the
    shift of the frame center (frame widths, right and down positive)."""

    scale: float = Field(gt=0)
    dx: float
    dy: float


class ZoomEvent(BaseModel):
    """A zoom from start to end seconds (end exclusive) that scales the
    picture by scale (> 1 in, < 1 out)."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    scale: float = Field(gt=0)
    kind: Literal["punch", "ramp"]


class ShakeSpan(BaseModel):
    """A shake from start to end seconds; amplitude is its largest frame
    shift in frame widths."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    amplitude: float = Field(ge=0)


class MotionStats(BaseModel):
    """The zooms and shakes of a video and how many come per minute."""

    zooms: list[ZoomEvent]
    shakes: list[ShakeSpan]
    zooms_per_minute: float = Field(ge=0)
    shakes_per_minute: float = Field(ge=0)


def pair_motion(first: Grey, second: Grey) -> PairMotion | None:
    """Return the motion from the grey frame first to second, or None if it
    cannot be estimated (module doc)."""
    found = cv2.goodFeaturesToTrack(
        first,
        maxCorners=MAX_CORNERS,
        qualityLevel=CORNER_QUALITY,
        minDistance=CORNER_DISTANCE,
    )
    if found is None or len(found) < MIN_POINTS:
        return None
    corners = np.asarray(found, dtype=np.float32)
    rough = _similarity(first, second, corners)
    if rough is None:
        return None
    height, width = first.shape
    # A big step (a punch) loses most corners; second warped back by the
    # rough estimate is close to first, so a second pass tracks them.
    back = cv2.invertAffineTransform(rough[0])
    aligned = np.asarray(cv2.warpAffine(second, back, (width, height)), np.uint8)
    fine = _similarity(first, aligned, corners)
    if fine is None or fine[1] < MIN_INLIER_SHARE:
        return None
    matrix = np.vstack([rough[0], [0, 0, 1]]) @ np.vstack([fine[0], [0, 0, 1]])
    center = np.array([width / 2, height / 2, 1.0])
    shift = (matrix @ center)[:2] - center[:2]
    return PairMotion(
        scale=round(math.hypot(matrix[0, 0], matrix[1, 0]), 6),
        dx=round(float(shift[0]) / width, 6),
        dy=round(float(shift[1]) / width, 6),
    )


def _similarity(
    first: Grey, second: Grey, corners: npt.NDArray[np.float32]
) -> tuple[npt.NDArray[np.float64], float] | None:
    """Return the similarity (2x3) that moves corners of first onto where
    they are in second, and the share of tracked corners that fit it; None
    if fewer than MIN_POINTS are tracked or no fit is found."""
    # Without OPTFLOW_USE_INITIAL_FLOW the next points passed in are not read.
    moved, status, _ = cv2.calcOpticalFlowPyrLK(first, second, corners, corners.copy())
    found = status.reshape(-1) == 1
    if int(found.sum()) < MIN_POINTS:
        return None
    matrix, inliers = cv2.estimateAffinePartial2D(
        corners[found],
        moved[found],
        method=cv2.RANSAC,
        ransacReprojThreshold=RANSAC_PIXELS,
    )
    if matrix is None:
        return None
    return matrix, int(inliers.sum()) / int(found.sum())


def scale_curve(pairs: Sequence[PairMotion | None]) -> list[float]:
    """Return the picture scale of each frame against frame 0: the product of
    the scales of the pairs up to it (pairs[k] is frame k - 1 to k; a pair
    without motion counts as 1)."""
    curve, scale = [], 1.0
    for pair in pairs:
        scale *= pair.scale if pair is not None else 1.0
        curve.append(round(scale, 6))
    return curve


def motion_stats(pairs: Sequence[PairMotion | None], fps: float) -> MotionStats:
    """Return the zooms and shakes of a video whose frame k (k / fps seconds)
    moved by pairs[k] from frame k - 1 (pairs[0] is None)."""
    zooms = zoom_events(pairs, fps)
    shakes = shake_spans(pairs, fps)
    minutes = len(pairs) / fps / 60
    return MotionStats(
        zooms=zooms,
        shakes=shakes,
        zooms_per_minute=round(len(zooms) / minutes, DECIMALS) if minutes else 0.0,
        shakes_per_minute=round(len(shakes) / minutes, DECIMALS) if minutes else 0.0,
    )


def zoom_events(pairs: Sequence[PairMotion | None], fps: float) -> list[ZoomEvent]:
    """Return the zooms of pairs (module doc), in order."""
    steps = [math.log(p.scale) if p is not None else 0.0 for p in pairs]
    events = []
    for sign in (1, -1):
        moving = [sign * step >= ZOOM_STEP for step in steps]
        for first, last in _bridged_runs(moving, ZOOM_GAP):
            change = sum(steps[first : last + 1])
            if abs(change) < ZOOM_MIN_CHANGE:
                continue
            frames = last + 1 - first
            events.append(
                ZoomEvent(
                    start=round(first / fps, DECIMALS),
                    end=round((last + 1) / fps, DECIMALS),
                    scale=round(math.exp(change), DECIMALS),
                    kind="punch" if frames <= PUNCH_FRAMES else "ramp",
                )
            )
    return sorted(events, key=lambda event: event.start)


def shake_spans(pairs: Sequence[PairMotion | None], fps: float) -> list[ShakeSpan]:
    """Return the shakes of pairs (module doc), in order."""
    shifts = [np.array([p.dx, p.dy]) if p is not None else np.zeros(2) for p in pairs]
    sizes = [float(np.linalg.norm(shift)) for shift in shifts]

    def turns(index: int, other: int) -> bool:
        """Return whether the shift of frame index turns back against other's."""
        return 0 <= other < len(shifts) and float(shifts[index] @ shifts[other]) < 0

    jolts = [
        sizes[k] >= SHAKE_STEP and (turns(k, k - 1) or turns(k, k + 1))
        for k in range(len(pairs))
    ]
    spans = []
    for first, last in _bridged_runs(jolts, SHAKE_GAP):
        if sum(jolts[first : last + 1]) < SHAKE_FRAMES:
            continue
        spans.append(
            ShakeSpan(
                start=round(first / fps, DECIMALS),
                end=round((last + 1) / fps, DECIMALS),
                amplitude=round(max(sizes[first : last + 1]), DECIMALS),
            )
        )
    return spans


def _bridged_runs(flags: Sequence[bool], gap: int) -> list[tuple[int, int]]:
    """Return the (first, last) indexes of the runs of true flags, joining
    runs separated by at most gap false flags."""
    runs: list[tuple[int, int]] = []
    for index, flag in enumerate(flags):
        if not flag:
            continue
        if runs and index - runs[-1][1] <= gap + 1:
            runs[-1] = (runs[-1][0], index)
        else:
            runs.append((index, index))
    return runs
