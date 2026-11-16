"""RGB split of a frame (SPEC-v3 4.3 flashes/glitches): the channel-offset
heuristic.

An RGB split moves the red and blue channels of a frame apart. The edges of
each channel (Sobel gradient magnitude of the channel blurred by EDGE_SIGMA
px) are matched against the green channel's over every shift up to
max_shift px each way (normalized cross-correlation, cv2.matchTemplate
TM_CCOEFF_NORMED); the best shift is that channel's offset. Matching the
raw channels (or phase correlation) misses the split after a yuv420p round
trip: the fine detail of every decoded channel comes from the shared luma,
and only the edges keep each channel's place.

A frame is split when red and blue lie at least MIN_SPLIT_PX apart and
each one's best shift matches green better than no shift by MIN_GAIN.
"""

import math
from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from clipforge.proedit.features.color import Frame

EDGE_SIGMA = 1.0
MAX_SHIFT = 16
MIN_SPLIT_PX = 2.0
MIN_GAIN = 0.1
Plane = npt.NDArray[np.float32]


@dataclass(frozen=True)
class ChannelOffset:
    """The offsets (dx, dy px; right and down are positive) of a frame's red
    and blue channels from its green, and by how much each matches green
    better there than unshifted (gain)."""

    red: tuple[int, int]
    blue: tuple[int, int]
    gain: float

    @property
    def split_px(self) -> float:
        """Return half the distance between red and blue: how far each
        moved from the middle."""
        return math.dist(self.red, self.blue) / 2

    @property
    def is_split(self) -> bool:
        """Return whether the frame shows an RGB split (module doc)."""
        return self.split_px * 2 >= MIN_SPLIT_PX and self.gain >= MIN_GAIN


def channel_edges(channel: npt.NDArray[np.uint8]) -> Plane:
    """Return the edge strength of each pixel of channel (module doc)."""
    blurred = np.asarray(
        cv2.GaussianBlur(channel.astype(np.float32), (0, 0), EDGE_SIGMA),
        dtype=np.float32,
    )
    dx = np.asarray(cv2.Sobel(blurred, cv2.CV_32F, 1, 0), dtype=np.float32)
    dy = np.asarray(cv2.Sobel(blurred, cv2.CV_32F, 0, 1), dtype=np.float32)
    return np.hypot(dx, dy).astype(np.float32)


def best_shift(
    moved: Plane, reference: Plane, max_shift: int
) -> tuple[tuple[int, int], float]:
    """Return the shift (dx, dy) with moved(p) closest to reference(p - shift)
    within max_shift px each way, and how much better it matches than no
    shift (normalized cross-correlation)."""
    height, width = moved.shape
    core = moved[max_shift : height - max_shift, max_shift : width - max_shift]
    scores = np.asarray(
        cv2.matchTemplate(reference, core, cv2.TM_CCOEFF_NORMED), dtype=np.float32
    )
    row, column = np.unravel_index(int(np.argmax(scores)), scores.shape)
    gain = float(scores[row, column] - scores[max_shift, max_shift])
    return (max_shift - int(column), max_shift - int(row)), gain


def channel_offset(rgb: Frame, max_shift: int = MAX_SHIFT) -> ChannelOffset:
    """Return the offsets of the red and blue channels of the RGB frame rgb
    [row, column, channel] from its green one (module doc)."""
    red, green, blue = (channel_edges(rgb[:, :, n]) for n in range(3))
    red_shift, red_gain = best_shift(red, green, max_shift)
    blue_shift, blue_gain = best_shift(blue, green, max_shift)
    return ChannelOffset(red_shift, blue_shift, min(red_gain, blue_gain))
