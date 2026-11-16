"""Skin-tone protection of a Pro Edit grade (SPEC-v3 3.3 color): in the
skin hue range a grade may change a color's saturation by at most
SKIN_MAX_CHANGE of it.

Colors are RGB triples in 0..1 (numpy arrays, last axis R, G, B).
Saturation is the chroma max - min of R, G, B (as proedit/features/color
measures it), hue the HSV hue in degrees. Skin hues are SKIN_HUE_LOW to
SKIN_HUE_HIGH degrees (reds through oranges to yellow-orange: light to
dark skin under daylight and tungsten), with a SKIN_FEATHER degree
fade-out on each side so the protection has no hard edge. Grays (no
chroma) have no hue and are not protected.

protect_skin caps the saturation of a graded color whose source color is
skin: the graded color's chroma is scaled about its own luma (Rec. 601) so
its saturation lies within SKIN_MAX_CHANGE of the source's (its hue and
luma stay as graded), weighted by how much of a skin hue the source is.
Where that color would leave the RGB gamut (a saturated skin color a look
darkens or brightens a lot) it is shifted back in, keeping its chroma and
giving up some of the grade's luma change instead.
The grade's LUT (fx_basic) is built from protected colors, so frames get
the same cap up to the LUT's interpolation between its grid points.
"""

import numpy as np
import numpy.typing as npt

Rgb = npt.NDArray[np.float64]
Values = npt.NDArray[np.float64]

SKIN_HUE_LOW = 5.0
SKIN_HUE_HIGH = 45.0
SKIN_FEATHER = 15.0
SKIN_MAX_CHANGE = 0.12
LUMA_WEIGHTS = np.array([0.299, 0.587, 0.114])
EPSILON = 1e-6


def luma(rgb: Rgb) -> Values:
    """Return the Rec. 601 luma of each color of rgb."""
    return np.asarray(rgb @ LUMA_WEIGHTS, dtype=np.float64)


def chroma(rgb: Rgb) -> Values:
    """Return the saturation (max - min of R, G, B) of each color of rgb."""
    return np.asarray(rgb.max(axis=-1) - rgb.min(axis=-1), dtype=np.float64)


def hue_degrees(rgb: Rgb) -> Values:
    """Return the HSV hue (0..360 degrees) of each color of rgb; 0 for grays."""
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    top = rgb.max(axis=-1)
    spread = chroma(rgb)
    safe = np.where(spread > 0, spread, 1.0)
    sector = np.where(
        top == red,
        ((green - blue) / safe) % 6,
        np.where(top == green, (blue - red) / safe + 2, (red - green) / safe + 4),
    )
    return np.asarray(np.where(spread > 0, sector * 60.0, 0.0), dtype=np.float64)


def skin_weight(rgb: Rgb) -> Values:
    """Return how much each color of rgb is a skin hue: 1 from SKIN_HUE_LOW
    to SKIN_HUE_HIGH degrees, fading to 0 SKIN_FEATHER degrees outside;
    0 for grays."""
    center = (SKIN_HUE_LOW + SKIN_HUE_HIGH) / 2
    half = (SKIN_HUE_HIGH - SKIN_HUE_LOW) / 2
    away = np.abs((hue_degrees(rgb) - center + 180.0) % 360.0 - 180.0)
    weight = np.clip(1.0 - np.maximum(away - half, 0.0) / SKIN_FEATHER, 0.0, 1.0)
    return np.asarray(np.where(chroma(rgb) > EPSILON, weight, 0.0), dtype=np.float64)


def protect_skin(source: Rgb, graded: Rgb, cap: float = SKIN_MAX_CHANGE) -> Rgb:
    """Return graded (the grade of the colors source) with the saturation of
    each skin color kept within cap (a share) of its source's (module doc)."""
    before, after = chroma(source), chroma(graded)
    target = np.clip(after, before * (1 - cap), before * (1 + cap))
    graded_luma = luma(graded)[..., None]
    source_luma = luma(source)[..., None]
    scale = np.where(after > EPSILON, target / np.where(after > EPSILON, after, 1.0), 0)
    regrown = np.where(
        before > EPSILON, target / np.where(before > EPSILON, before, 1.0), 0
    )
    rescaled = np.where(
        (after > EPSILON)[..., None],
        graded_luma + (graded - graded_luma) * scale[..., None],
        graded_luma + (source - source_luma) * regrown[..., None],
    )
    below = np.maximum(-rescaled.min(axis=-1), 0.0)
    above = np.maximum(rescaled.max(axis=-1) - 1.0, 0.0)
    inside = rescaled + (below - above)[..., None]
    weight = skin_weight(source)[..., None]
    return np.asarray(np.clip(graded + weight * (inside - graded), 0.0, 1.0))


def scale_chroma(rgb: Rgb, scale: float) -> Rgb:
    """Return rgb with its chroma scaled by scale about each color's luma (a
    luma-keeping saturation change, as ffmpeg's hue=s does in YUV)."""
    level = luma(rgb)[..., None]
    return np.asarray(np.clip(level + (rgb - level) * scale, 0.0, 1.0))
