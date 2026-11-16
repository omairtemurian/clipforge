"""Basic effects of a Pro Edit render (SPEC-v3 3.3, 3.6): freeze frames and
flashes (fx track), and the color steps that a grade change (grade.py)
runs: auto exposure/white-balance normalization first, then its look, the
LUT looks and the skin-tone protection (skin.py) of looks that change
saturation.

Filters (verified with `ffmpeg -h filter=<name>` and their sources,
ffmpeg 9.0.2; docs/decisions.md):
- freeze_frame: `freezeframes` replaces the frames first..last of its
  first input with frame `replace` of its second (frame numbers count from
  0, the clip's first frame; timing.frame_range). Both inputs are the
  stream, split; the filter keeps reading the second, so nothing piles up.
  It has no timeline option. Frames keep their times: the clip's length
  does not change.
- flash: `eq` with per-frame (eval=frame) expressions of t, enabled on the
  window: brightness up (white) or down (black) by peak on the window's
  first frame and saturation down by as much, fading linearly to nothing
  at the window's end.
- normalize: `normalize` (RGB) stretches each frame's levels toward the
  full range (exposure), each channel from its own black and white points
  (independence 1: a channel a cast holds down is lifted more, which
  evens the white balance), at strength 0.5 (half way, so colorful scenes
  keep most of their color) and smoothed over half a second against
  flicker. `colorbalance` and `colortemperature` were checked but need a
  known cast or temperature, which a clip does not give.
- LUTs: `lut3d=file=<.cube>:interp=tetrahedral`. A lut look at amount 1
  without skin protection reads its bundled file; otherwise, and for the
  protected saturation of desat/dark, a derived LUT (amount of the way
  from no change to the look, skin colors capped by skin.protect_skin) is
  written once to LUT_CACHE_DIRNAME in the data directory, named after
  its contents, so the same item always reads the same file.

normalize and lut3d work on RGB; the grade stage turns the chain back to
YUV_FORMAT after them (RGB_FILTERS) so later filters see YUV.
"""

import hashlib
import os
from collections.abc import Sequence
from pathlib import Path

from clipforge import config
from clipforge.ffmpeg import filter_value
from clipforge.proedit.edl import FlashItem, TypedEdlItem
from clipforge.proedit.render.luts import (
    bundled_path,
    bundled_values,
    cube_text,
    identity_grid,
)
from clipforge.proedit.render.skin import Rgb, protect_skin, scale_chroma
from clipforge.proedit.render.timing import enable, frame_range

YUV_FORMAT = "format=yuv420p"
RGB_FILTERS = ("normalize=", "lut3d=")
LUT_CACHE_DIRNAME = Path("proedit") / "luts"
NORMALIZE_INDEPENDENCE = 1.0
NORMALIZE_STRENGTH = 0.5
DECIMALS = 4
TIME_DECIMALS = 6


def number(value: float) -> str:
    """Return value with at most DECIMALS decimals and no trailing zeros."""
    return f"{round(value, DECIMALS):g}"


def freeze_filters(items: Sequence[TypedEdlItem], fps: int) -> list[str]:
    """Return the filters that hold, for each freeze_frame item, the frame
    at its start on every frame of its window (at fps)."""
    filters = []
    ranked = sorted(items, key=lambda i: (i.t_start, i.id))
    for index, item in enumerate(ranked):
        first, end = frame_range(item.t_start, item.t_end, fps)
        if end <= first:
            continue
        held, source = f"[pe_freeze{index}]", f"[pe_held{index}]"
        filters.append(
            f"split{held}{source};{held}{source}"
            f"freezeframes=first={first}:last={end - 1}:replace={first}"
        )
    return filters


def flash_filter(item: FlashItem, fps: int) -> str:
    """Return the filter of one flash (module doc), at fps."""
    first, end = frame_range(item.t_start, item.t_end, fps)
    start, length = first / fps, max(end - first, 1) / fps
    fade = f"clip(1-(t-{start:.{TIME_DECIMALS}f})/{length:.{TIME_DECIMALS}f},0,1)"
    peak = number(item.params.peak)
    sign = "" if item.params.color == "white" else "-"
    return (
        f"eq=brightness='{sign}{peak}*{fade}':saturation='1-{peak}*{fade}'"
        f":eval=frame:{enable(item.t_start, item.t_end, fps)}"
    )


def flash_filters(items: Sequence[TypedEdlItem], fps: int) -> list[str]:
    """Return the filters of the flash items, in time order."""
    flashes = [i for i in items if isinstance(i, FlashItem)]
    return [flash_filter(i, fps) for i in sorted(flashes, key=lambda i: i.t_start)]


def no_problems(items: Sequence[TypedEdlItem]) -> list[str]:
    """Return no problems: every item of the stage can be drawn."""
    return []


def normalize_filter(fps: int) -> str:
    """Return the auto exposure/white-balance filter (module doc) at fps."""
    return (
        f"normalize=smoothing={max(fps // 2, 1)}"
        f":independence={number(NORMALIZE_INDEPENDENCE)}"
        f":strength={number(NORMALIZE_STRENGTH)}"
    )


def lut_filter(cube: Path) -> str:
    """Return the filter that grades with the .cube file cube."""
    return f"lut3d=file={filter_value(str(cube.absolute()))}:interp=tetrahedral"


def leaves_rgb(filters: Sequence[str]) -> bool:
    """Return whether any of filters works on RGB (RGB_FILTERS)."""
    return any(f.startswith(RGB_FILTERS) for f in filters)


def look_lut(name: str, amount: float, skin_protect: bool) -> Path:
    """Return the .cube file of the bundled look name at amount (0..1],
    skin colors protected if skin_protect."""
    if amount == 1 and not skin_protect:
        return bundled_path(name)
    source = identity_grid()
    graded = source + (bundled_values(name) - source) * amount
    if skin_protect:
        graded = protect_skin(source, graded)
    return cached_lut(f"ClipForge {name} {number(amount)}", graded)


def saturation_lut(scale: float) -> Path:
    """Return the .cube file that scales saturation by scale except in skin
    colors (skin.protect_skin)."""
    source = identity_grid()
    graded = protect_skin(source, scale_chroma(source, scale))
    return cached_lut(f"ClipForge saturation {number(scale)}", graded)


def cached_lut(title: str, values: Rgb) -> Path:
    """Return the derived LUT file of values (luts.cube_text), written once
    to the LUT cache, named after its contents."""
    text = cube_text(title, values)
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    path = config.settings.data_dir / LUT_CACHE_DIRNAME / f"{digest}.cube"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
        partial.write_text(text)
        os.replace(partial, path)
    return path
