"""The grade track of a Pro Edit render (SPEC-v3 3.3 color): grade changes
(black and white, dark, desaturated, bundled LUT looks), vignette and film
grain, each drawn only on the frames of its item's window (timing.enable).

A grade change first normalizes exposure and white balance (if its
normalize param is set; fx_basic.normalize_filter), then draws its look.
Looks that change saturation keep skin colors within skin.SKIN_MAX_CHANGE
of their saturation when skin_protect is set (the default): desat and the
dark look's saturation then go through a protected saturation LUT, a lut
look through its protected derived LUT (fx_basic). Black and white takes
all color by design and is never protected.

Filters (verified with `ffmpeg -h filter=<name>`, ffmpeg 9.0.2, all with
timeline support; docs/decisions.md):
- bw: `hue=s=0`, no chroma at all (saturation 0 at amount 1);
- desat: `hue=s=<1 - DESAT_LOSS * amount>` (unprotected);
- dark: `eq` with a lower gamma (the midtones go down, eq's lut raises
  each level to 1/gamma), a little lower brightness, a little more
  contrast and (unprotected) less saturation;
- lut: `lut3d` (fx_basic.lut_filter) with a bundled look (luts.LOOKS);
- vignette: `vignette=angle=<strength * pi/2>`; the angle is clipped to
  0..pi/2, so strength 1 is the darkest edge and the default 0.4 is
  vignette's own default pi/5;
- grain: `noise` on the luma plane only (c0: the chain is back in yuv420p
  after the grade changes, so the chroma and a black and white window stay
  as they are), temporal (a new pattern every frame) and seeded (c0_seed,
  0..INT_MAX; -1 would be random), so the same plan gives the same frames.
"""

import math
from collections.abc import Sequence

from clipforge.proedit import edl_params as p
from clipforge.proedit.edl import GradeChangeItem, GrainItem, TypedEdlItem, VignetteItem
from clipforge.proedit.render import fx_basic
from clipforge.proedit.render.fx_basic import number
from clipforge.proedit.render.luts import LOOKS as LUT_LOOKS
from clipforge.proedit.render.timing import enable

DESAT_LOSS = 0.6
DARK_BRIGHTNESS = -0.06
DARK_CONTRAST = 0.1
DARK_GAMMA = 0.35
DARK_SATURATION = 0.2
VIGNETTE_MAX_ANGLE = math.pi / 2
GRAIN_MAX = 50
NOISE_SEEDS = 2**31
ORDER = {"grade_change": 0, "vignette": 1, "grain": 2}


def bw_filter(amount: float) -> str:
    """Return the filter that takes amount (0..1] of the color away; all of
    it at 1."""
    return f"hue=s={number(1 - amount)}"


def desat_filter(amount: float) -> str:
    """Return the filter that takes DESAT_LOSS * amount of the color away."""
    return f"hue=s={number(1 - DESAT_LOSS * amount)}"


def dark_filter(amount: float, saturation: bool = True) -> str:
    """Return the filter of the dark look at amount (0..1]: lower exposure
    (gamma and brightness), a little more contrast and, if saturation, less
    saturation."""
    look = (
        f"eq=brightness={number(DARK_BRIGHTNESS * amount)}"
        f":contrast={number(1 + DARK_CONTRAST * amount)}"
        f":gamma={number(1 - DARK_GAMMA * amount)}"
    )
    if saturation:
        look += f":saturation={number(1 - DARK_SATURATION * amount)}"
    return look


def look_filters(params: p.GradeChangeParams) -> list[str]:
    """Return the filters of a grade change's look (module doc), without
    its normalization."""
    amount, protect = params.amount, params.skin_protect
    if params.look == "bw":
        return [bw_filter(amount)]
    if params.look == "desat":
        if protect:
            return [
                fx_basic.lut_filter(fx_basic.saturation_lut(1 - DESAT_LOSS * amount))
            ]
        return [desat_filter(amount)]
    if params.look == "dark":
        if protect:
            scale = 1 - DARK_SATURATION * amount
            return [
                dark_filter(amount, saturation=False),
                fx_basic.lut_filter(fx_basic.saturation_lut(scale)),
            ]
        return [dark_filter(amount)]
    if params.lut is None or params.lut not in LUT_LOOKS:
        raise ValueError(f"the lut {params.lut} is not bundled")
    return [fx_basic.lut_filter(fx_basic.look_lut(params.lut, amount, protect))]


def vignette_filter(params: p.VignetteParams) -> str:
    """Return the vignette of strength (0..1]: lens angle strength * pi/2."""
    return f"vignette=angle={number(params.strength * VIGNETTE_MAX_ANGLE)}"


def grain_filter(params: p.GrainParams) -> str:
    """Return the luma grain of strength (0..1] (noise strength up to
    GRAIN_MAX of 100), new every frame, from the item's seed."""
    strength = max(1, round(params.strength * GRAIN_MAX))
    return f"noise=c0s={strength}:c0f=t:c0_seed={params.seed % NOISE_SEEDS}"


def item_filters(item: TypedEdlItem, fps: int) -> list[str]:
    """Return the filters of one grade-track item at fps, without its
    window. Raises ValueError for an item of another track or a lut that
    is not bundled."""
    if isinstance(item, GradeChangeItem):
        first = [fx_basic.normalize_filter(fps)] if item.params.normalize else []
        return first + look_filters(item.params)
    if isinstance(item, VignetteItem):
        return [vignette_filter(item.params)]
    if isinstance(item, GrainItem):
        return [grain_filter(item.params)]
    raise ValueError(f"item {item.id} ({item.kind}) is not on the grade track")


def grade_filters(items: Sequence[TypedEdlItem], fps: int) -> list[str]:
    """Return the filters of the grade-track items, in time order, each
    enabled only on its window's frames: the grade changes first (back to
    fx_basic.YUV_FORMAT if one of them works on RGB), then the vignettes,
    then the grain, so grain is never graded away."""
    filters: list[str] = []
    ranked = sorted(items, key=lambda i: (ORDER[i.kind], i.t_start, i.id))
    for kind in ORDER:
        for item in (i for i in ranked if i.kind == kind):
            window = enable(item.t_start, item.t_end, fps)
            filters += [f"{f}:{window}" for f in item_filters(item, fps)]
        if kind == "grade_change" and fx_basic.leaves_rgb(filters):
            filters.append(fx_basic.YUV_FORMAT)
    return filters


def grade_problems(items: Sequence[TypedEdlItem]) -> list[str]:
    """Return why grade-track items cannot be drawn (luts not bundled)."""
    return [
        f"item {item.id} (grade_change): the lut {item.params.lut} is not "
        f"bundled with the Pro Edit renderer"
        for item in items
        if isinstance(item, GradeChangeItem)
        and item.params.look == "lut"
        and item.params.lut not in LUT_LOOKS
    ]
