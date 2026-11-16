"""The reasons a crop keyframe (sample) of an auto fill scene wants a zoom
out (pipeline/layout_auto, TASK-198), and the thresholds of an intensity.

- spread: two or more faces spread wider than the fill window;
- wide: a wide or establishing shot, whose largest face is less tall than
  wide_face_height of the frame;
- motion: nobody seen, but at least motion_spread of the frame's columns
  move (wide action, sports, gameplay without a facecam);
- lost: nobody seen for longer than lost_s in a shot that shows someone
  elsewhere (the tracker lost the subject).

(On-screen text wider than the crop is not a reason: there is no OCR.)
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from clipforge.models import CropKeyframe, FaceBox, ZoomOutIntensity
from clipforge.zoom_out_settings import ZoomOutSettings

Reason = Literal["spread", "wide", "motion", "lost"]
# A motion sample further than this (seconds) from a keyframe does not count.
MOTION_REACH_S = 0.5


@dataclass(frozen=True)
class MotionSample:
    """The share of the frame's columns that move at t source seconds."""

    t: float
    spread: float


@dataclass(frozen=True)
class ZoomOutParams:
    """The thresholds of one intensity (module docstring)."""

    max_share: float
    min_segment_s: float
    wide_face_height: float
    lost_s: float
    motion_spread: float
    enter: float
    exit: float
    window_s: float


def zoom_params(
    intensity: ZoomOutIntensity, cfg: ZoomOutSettings
) -> ZoomOutParams | None:
    """Return the thresholds of intensity: cfg's scaled by its factor f
    (max share and wide-face height times f, lost time over f, the
    unmoving share of columns times f); None for off."""
    if intensity == "off":
        return None
    factor = cfg.intensity_factors.get(intensity, 1.0)
    return ZoomOutParams(
        max_share=min(1.0, cfg.max_share * factor),
        min_segment_s=cfg.min_segment_s,
        wide_face_height=min(1.0, cfg.wide_face_height * factor),
        lost_s=cfg.lost_s / factor,
        motion_spread=max(0.0, 1 - (1 - cfg.motion_spread) * factor),
        enter=cfg.enter,
        exit=cfg.exit,
        window_s=cfg.window_s,
    )


def sample_reasons(
    samples: Sequence[CropKeyframe],
    frame_size: tuple[int, int],
    fill_width: int,
    motion: Sequence[MotionSample],
    params: ZoomOutParams,
) -> list[tuple[Reason | None, bool]]:
    """Return why each of samples (one shot's, in order) wants a zoom out
    (module docstring), or None, and whether it needs the whole frame (fit),
    in a frame_size source whose fill window is fill_width wide."""
    frame_width, frame_height = frame_size
    side = min(frame_size)
    seen = [[f for f in k.faces if f.kind != "object"] for k in samples]
    lost = _lost_flags(samples, seen, params.lost_s)
    reasons: list[tuple[Reason | None, bool]] = []
    for sample, found, is_lost in zip(samples, seen, lost, strict=True):
        faces = [face for face in found if face.kind == "face"]
        span = _span(faces)
        if len(faces) >= 2 and span > fill_width and fill_width < frame_width:
            reasons.append(("spread", span > side))
        elif faces and max(f.height for f in faces) < (
            params.wide_face_height * frame_height
        ):
            reasons.append(("wide", span > side))
        elif not found and _spread_at(motion, sample.t) >= params.motion_spread:
            reasons.append(("motion", True))
        elif is_lost:
            reasons.append(("lost", False))
        else:
            reasons.append((None, False))
    return reasons


def _lost_flags(
    samples: Sequence[CropKeyframe],
    seen: Sequence[Sequence[FaceBox]],
    lost_s: float,
) -> list[bool]:
    """Return whether each sample is in a run without anyone seen that lasts
    longer than lost_s, in a shot that shows someone in another sample."""
    flags = [False] * len(samples)
    if not any(seen):
        return flags
    index = 0
    while index < len(samples):
        if seen[index]:
            index += 1
            continue
        end = index
        while end + 1 < len(samples) and not seen[end + 1]:
            end += 1
        after = samples[end + 1].t if end + 1 < len(samples) else samples[end].t
        if after - samples[index].t > lost_s:
            flags[index : end + 1] = [True] * (end + 1 - index)
        index = end + 1
    return flags


def _span(faces: Sequence[FaceBox]) -> float:
    """Return the width, in source pixels, from the left edge of the
    leftmost of faces to the right edge of the rightmost; 0 if none."""
    if not faces:
        return 0.0
    return max(f.x + f.width for f in faces) - min(f.x for f in faces)


def _spread_at(motion: Sequence[MotionSample], t: float) -> float:
    """Return the motion spread of the sample of motion nearest to t, or 0
    if none is within MOTION_REACH_S."""
    near = [m for m in motion if abs(m.t - t) <= MOTION_REACH_S]
    if not near:
        return 0.0
    return min(near, key=lambda m: abs(m.t - t)).spread
