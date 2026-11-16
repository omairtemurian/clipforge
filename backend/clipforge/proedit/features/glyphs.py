"""The caption glyphs of a frame (SPEC-v3 4.3 captions), as a mask OCR can
read.

Burned-in short-form captions are bright or colored letters inside a dark
outline (a stroke, a shadow or a dark box). The pixels of a frame lighter
than OUTLINE_LUMA (0..255 luma) form 4-connected components; a letter's
fill is one that the dark outline encloses: it does not touch the frame's
edge and has a glyph's size (MIN_GLYPH_HEIGHT..MAX_GLYPH_HEIGHT of the
frame height, at most MAX_GLYPH_WIDTH of its width, at least MIN_FILL of
its box filled). The background showing through a letter's counter (the
hole of an "o") is enclosed too: a component whose box lies strictly
inside another's is dropped. Large background areas touch the edge or are
too big and are left out.

The mask is the kept fills drawn black on white, each thickened by
THICKEN of the median fill height so letters sit as close as in the
original font (the outline kept them apart) and OCR splits words as
printed. Captions without a dark outline (plain text on a light picture,
dark text on a light box) are not found.
"""

from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from clipforge.proedit.features.color import Frame

OUTLINE_LUMA = 60
MIN_GLYPH_HEIGHT = 0.008
MAX_GLYPH_HEIGHT = 0.15
MAX_GLYPH_WIDTH = 0.25
MIN_FILL = 0.1
THICKEN = 0.06

Grey = npt.NDArray[np.uint8]
Labels = npt.NDArray[np.int32]


@dataclass(frozen=True)
class Glyphs:
    """The caption glyph fills of a frame: labels[row, column] is the
    component of each pixel, boxes[k] the (left, top, width, height) box of
    the kept component ids[k], and mask the OCR image (module doc)."""

    labels: Labels
    ids: npt.NDArray[np.int32]
    boxes: npt.NDArray[np.int32]
    mask: Grey

    def inside(self, left: int, top: int, width: int, height: int) -> list[int]:
        """Return the indexes (into ids/boxes) of the glyphs whose center
        lies inside the box (left, top, width, height)."""
        if not len(self.ids):
            return []
        centers_x = self.boxes[:, 0] + self.boxes[:, 2] / 2
        centers_y = self.boxes[:, 1] + self.boxes[:, 3] / 2
        hit = (
            (centers_x >= left)
            & (centers_x <= left + width)
            & (centers_y >= top)
            & (centers_y <= top + height)
        )
        return [int(k) for k in np.flatnonzero(hit)]


def find_glyphs(rgb: Frame) -> Glyphs:
    """Return the caption glyphs of the RGB frame rgb (module doc)."""
    height, width = rgb.shape[:2]
    grey = np.asarray(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), dtype=np.uint8)
    light = (grey > OUTLINE_LUMA).astype(np.uint8)
    _, found, found_stats, _ = cv2.connectedComponentsWithStats(light, connectivity=4)
    labels = np.asarray(found, dtype=np.int32)
    stats = np.asarray(found_stats, dtype=np.int32)
    left, top, w, h, area = (stats[:, k] for k in range(5))
    sized = (
        (left > 0)
        & (top > 0)
        & (left + w < width)
        & (top + h < height)
        & (h >= MIN_GLYPH_HEIGHT * height)
        & (h <= MAX_GLYPH_HEIGHT * height)
        & (w <= MAX_GLYPH_WIDTH * width)
        & (area >= MIN_FILL * w * h)
    )
    sized[0] = False
    ids = np.flatnonzero(sized).astype(np.int32)
    ids = ids[~_counters(stats[ids, :4])]
    boxes = stats[ids, :4]
    return Glyphs(labels, ids, boxes, _mask(labels, ids, boxes))


def _counters(boxes: npt.NDArray[np.int32]) -> npt.NDArray[np.bool_]:
    """Return for each box whether it lies strictly inside another one."""
    if not len(boxes):
        return np.zeros(0, dtype=bool)
    left, top = boxes[:, 0], boxes[:, 1]
    right, bottom = left + boxes[:, 2], top + boxes[:, 3]
    inside = (
        (left[:, None] > left[None, :])
        & (top[:, None] > top[None, :])
        & (right[:, None] < right[None, :])
        & (bottom[:, None] < bottom[None, :])
    )
    return np.asarray(inside.any(axis=1), dtype=bool)


def _mask(
    labels: Labels, ids: npt.NDArray[np.int32], boxes: npt.NDArray[np.int32]
) -> Grey:
    """Return the kept fills, thickened, black on white."""
    fills = np.isin(labels, ids).astype(np.uint8)
    if len(ids):
        radius = max(1, round(THICKEN * float(np.median(boxes[:, 3]))))
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1)
        )
        fills = np.asarray(cv2.dilate(fills, kernel), dtype=np.uint8)
    return np.where(fills > 0, 0, 255).astype(np.uint8)
