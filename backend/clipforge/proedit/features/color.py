"""Color features of a video (SPEC-v3 4.3): luma, contrast, saturation and
black-and-white frames, measured per sampled frame and summed up.

luma is the Rec. 601 luma (0.299 R + 0.587 G + 0.114 B) over 255, contrast
the standard deviation of a frame's luma. saturation is the mean chroma,
(max - min of R, G, B) over 255, rather than HSV saturation, which is noise
in dark pixels (RGB 2, 0, 0 has HSV saturation 1). A frame is black and white
when its saturation is below BW_SATURATION; runs of such frames are the B&W
spans.
"""

from collections.abc import Iterable, Sequence

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field

from clipforge.models import UnitInterval

BW_SATURATION = 0.03
DECIMALS = 4
LUMA_WEIGHTS = np.array([0.299, 0.587, 0.114], dtype=np.float32)

Frame = npt.NDArray[np.uint8]


class FrameColor(BaseModel):
    """The color of one frame: mean luma, contrast and saturation (0..1)."""

    luma: UnitInterval
    contrast: UnitInterval
    saturation: UnitInterval


class Span(BaseModel):
    """A stretch of a video from start to end seconds."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)


class ColorStats(BaseModel):
    """The color of a video: means over its frames (0..1), the share of B&W
    frames and the B&W spans."""

    mean_luma: UnitInterval
    contrast: UnitInterval
    saturation: UnitInterval
    bw_share: UnitInterval
    bw_spans: list[Span]


def luma_plane(rgb: Frame) -> npt.NDArray[np.float32]:
    """Return the luma (0..255) of each pixel of rgb [row, column, channel]."""
    return np.asarray(rgb, dtype=np.float32) @ LUMA_WEIGHTS


def frame_color(rgb: Frame) -> FrameColor:
    """Return the color of the RGB frame rgb (module doc)."""
    luma = luma_plane(rgb) / 255
    chroma = (rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2)) / 255
    return FrameColor(
        luma=round(float(luma.mean()), DECIMALS),
        contrast=round(float(luma.std()), DECIMALS),
        saturation=round(float(chroma.mean()), DECIMALS),
    )


def color_stats(frames: Sequence[FrameColor], fps: float) -> ColorStats:
    """Return the color of a video whose frame k (k / fps seconds) has the
    color frames[k]."""
    if not frames:
        return ColorStats(
            mean_luma=0, contrast=0, saturation=0, bw_share=0, bw_spans=[]
        )
    bw = [frame.saturation < BW_SATURATION for frame in frames]
    return ColorStats(
        mean_luma=_mean(frame.luma for frame in frames),
        contrast=_mean(frame.contrast for frame in frames),
        saturation=_mean(frame.saturation for frame in frames),
        bw_share=round(sum(bw) / len(bw), DECIMALS),
        bw_spans=[Span(start=a, end=b) for a, b in runs(bw, fps)],
    )


def runs(flags: Sequence[bool], fps: float) -> list[tuple[float, float]]:
    """Return the runs of true flags as (start, end) seconds: frame k is
    k / fps to (k + 1) / fps."""
    spans: list[tuple[float, float]] = []
    first: int | None = None
    for index, flag in enumerate([*flags, False]):
        if flag and first is None:
            first = index
        elif not flag and first is not None:
            spans.append((round(first / fps, DECIMALS), round(index / fps, DECIMALS)))
            first = None
    return spans


def _mean(values: Iterable[float]) -> float:
    """Return the mean of values, rounded."""
    return round(float(np.mean(list(values))), DECIMALS)
