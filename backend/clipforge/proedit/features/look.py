"""Vignette and grain of a video (SPEC-v3 4.3 color): per-frame estimates
whose median over a video's frames is its look.

Vignette: the renderer's vignette (ffmpeg `vignette`, render/grade.py)
multiplies the limited-range luma Y (16..235) of a pixel at distance d from
the center (in half-diagonals) by cos(angle * d) ** 4, so its full-range
luma L becomes f * (L + BLACK) - BLACK. A frame's outer to inner ratio of
L + BLACK (the corners, d >= OUTER, against the middle, d <= INNER) is
matched to the same ratio of that model on the frame's pixel grid; the
angle found over pi/2 is the strength (render/grade.py VignetteParams: 0
none, 1 the corners black). A frame brighter at the corners than in the
middle has strength 0; frames darker than DARK_LUMA in the middle have none.
Dark content in the corners reads as a vignette, too.

Grain: the luma noise level (0..1) of a frame at its own resolution, the
robust form of Immerkaer's estimate: the frame is filtered with the
Laplacian-difference kernel NOISE_KERNEL (flat areas and straight edges
give 0, white noise of sigma s gives 6 s), and sigma is 1.4826 times the
median of the absolute response, over 6. The median ignores the edges of
the picture as long as they cover less than half of it.
"""

import math
from functools import lru_cache

import cv2
import numpy as np
import numpy.typing as npt

from clipforge.proedit.features.color import Frame, luma_plane

BLACK = 16 * 255 / 219
INNER = 0.35
OUTER = 0.85
DARK_LUMA = 8.0
ANGLE_STEPS = 181
NOISE_KERNEL = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float32)
MAD_TO_SIGMA = 1.4826
DECIMALS = 4

Floats = npt.NDArray[np.float64]


def vignette_strength(rgb: Frame) -> float | None:
    """Return the vignette strength (0..1) of the RGB frame rgb (module
    doc), or None if its middle is too dark to tell."""
    height, width = rgb.shape[:2]
    inner, outer = _rings(height, width)
    luma = luma_plane(rgb)
    middle = float(luma[inner].mean())
    if middle < DARK_LUMA:
        return None
    ratio = (float(luma[outer].mean()) + BLACK) / (middle + BLACK)
    angles, ratios = _model(height, width)
    # ratios falls as the angle grows; np.interp needs rising x values.
    angle = float(np.interp(ratio, ratios[::-1], angles[::-1]))
    return round(angle / (math.pi / 2), DECIMALS)


def grain_sigma(rgb: Frame) -> float:
    """Return the luma noise level (0..1) of the RGB frame rgb (module doc)."""
    luma = luma_plane(rgb)
    if min(luma.shape) < 3:
        return 0.0
    response = np.asarray(cv2.filter2D(luma, -1, NOISE_KERNEL), dtype=np.float32)
    inside = np.abs(response[1:-1, 1:-1])
    return round(float(MAD_TO_SIGMA * np.median(inside) / 6 / 255), DECIMALS)


def _distances(height: int, width: int) -> Floats:
    """Return each pixel's distance from the frame center in half-diagonals."""
    rows, columns = np.mgrid[0:height, 0:width].astype(np.float64)
    radius = math.hypot(width / 2, height / 2)
    centered = np.hypot(columns + 0.5 - width / 2, rows + 0.5 - height / 2)
    return np.asarray(centered / radius, dtype=np.float64)


@lru_cache(maxsize=8)
def _rings(
    height: int, width: int
) -> tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_]]:
    """Return the masks of the middle (d <= INNER) and corner (d >= OUTER)
    pixels of a height x width frame."""
    distance = _distances(height, width)
    return distance <= INNER, distance >= OUTER


@lru_cache(maxsize=8)
def _model(height: int, width: int) -> tuple[Floats, Floats]:
    """Return the angles 0..pi/2 and, for each, the corner to middle ratio
    of the vignette model on a height x width frame."""
    distance = _distances(height, width)
    inner, outer = _rings(height, width)
    angles = np.linspace(0.0, math.pi / 2, ANGLE_STEPS)
    ratios = np.array(
        [
            float((np.cos(a * distance[outer]) ** 4).mean())
            / float((np.cos(a * distance[inner]) ** 4).mean())
            for a in angles
        ]
    )
    return angles, ratios
