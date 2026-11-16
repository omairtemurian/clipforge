"""Glitches and RGB splits of a Pro Edit render (SPEC-v3 3.3 Glitch): the fx
track's glitch and rgb_split items and the glitch frames of glitch
transitions (fx_transition.py).

Each item is drawn on its window only (window.over_window): a copy of the
stream is cut to the window's frames (`trim` start_frame/end_frame,
`setpts` from 0) and changed in RGB (`format=gbrp`). Frames outside the
windows are not touched.

- rgb_split: `rgbashift` moves red by the offset (offset_px of a
  REFERENCE_WIDTH frame, scaled to the canvas; at least a pixel) at
  angle_deg (0 = right, 90 = up) and blue the opposite way; edges smear.
- glitch, seeded by params.seed and the window's first frame
  (random.Random), so the same item always glitches the same way:
  - stutter: in a window of at least STUTTER_MIN_FRAMES frames, a run of
    STUTTER_SIZE frames at a random place plays 1 + round(STUTTER_REPEATS *
    strength) more times (`shuffleframes` mapping, which repeats frames of
    a block); the rest of the window plays that much behind the clip and
    snaps back at t_end, like a slow-mo (the sound runs on).
  - glitch frames: the window's first frame and each other one with chance
    GLITCH_SHARE + GLITCH_SHARE_SPAN * strength: BANDS + round(BANDS_SPAN *
    strength) horizontal bands (BAND_MIN..BAND_MAX of the height each) slid
    sideways by SLIDE_MIN..1 of SLIDE_MAX * strength of the width, and red
    and blue pulled apart sideways by SPLIT_MIN..1 of SPLIT_MAX * strength
    of the width (`geq` r/g/b expressions, enabled on that frame only;
    pixels beyond an edge repeat the edge).
- datamosh: no ffmpeg filter keeps motion vectors and drops a key frame
  inside a filter graph (`ffmpeg -filters`, 9.0.2), so a datamosh look is
  not supported (docs/decisions.md).
"""

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from clipforge.pipeline.layout_parts import balanced_sum
from clipforge.proedit.edl import (
    GlitchItem,
    RgbSplitItem,
    TransitionItem,
    TypedEdlItem,
)
from clipforge.proedit.edl_params import GlitchParams
from clipforge.proedit.render.canvas import Canvas
from clipforge.proedit.render.timing import frame_range
from clipforge.proedit.render.window import over_window, window_frames

RGB_FORMAT = "format=gbrp"
REFERENCE_WIDTH = 1080
STUTTER_MIN_FRAMES = 4
STUTTER_SIZE = 2
STUTTER_REPEATS = 2
GLITCH_SHARE = 0.3
GLITCH_SHARE_SPAN = 0.5
BANDS = 2
BANDS_SPAN = 4
BAND_MIN = 0.02
BAND_MAX = 0.12
SLIDE_MAX = 0.15
SLIDE_MIN = 0.3
SPLIT_MAX = 0.02
SPLIT_MIN = 0.5
# Glitch transitions get these glitch frames on their window.
TRANSITION_GLITCH = GlitchParams(strength=0.6)


@dataclass(frozen=True)
class FrameGlitch:
    """One glitch frame: bands (top, bottom, slide px) and the sideways
    split px of red (blue moves the other way)."""

    bands: tuple[tuple[int, int, int], ...]
    split: int


@dataclass(frozen=True)
class GlitchWindow:
    """What a glitch window plays: frames[k] is the window frame shown on
    its frame k (stutter), glitches the glitch frames by window frame."""

    frames: tuple[int, ...]
    glitches: dict[int, FrameGlitch]


def stutter_frames(count: int, strength: float, rng: random.Random) -> list[int]:
    """Return the window frame shown on each of the count frames of a glitch
    window of strength (module doc)."""
    if count < STUTTER_MIN_FRAMES:
        return list(range(count))
    start = rng.randrange(count - STUTTER_SIZE)
    run = list(range(start, start + STUTTER_SIZE))
    frames = list(range(start)) + run * (2 + round(STUTTER_REPEATS * strength))
    frames += range(start + STUTTER_SIZE, count)
    return frames[:count]


def frame_glitch(
    strength: float, size: tuple[int, int], rng: random.Random
) -> FrameGlitch:
    """Return a random glitch frame of strength at size (module doc)."""
    width, height = size
    bands = []
    for _ in range(BANDS + round(BANDS_SPAN * strength)):
        band = round(height * rng.uniform(BAND_MIN, BAND_MAX))
        top = rng.randrange(max(height - band, 1))
        slide = width * SLIDE_MAX * strength * rng.uniform(SLIDE_MIN, 1)
        bands.append((top, top + band, round(slide) * rng.choice((-1, 1))))
    split = width * SPLIT_MAX * strength * rng.uniform(SPLIT_MIN, 1)
    return FrameGlitch(tuple(bands), max(round(split), 1) * rng.choice((-1, 1)))


def glitch_window(
    params: GlitchParams, first: int, count: int, size: tuple[int, int]
) -> GlitchWindow:
    """Return what the glitch with params plays on the count frames of its
    window from frame first, at size (module doc)."""
    rng = random.Random(f"glitch:{params.seed}:{first}")
    frames = stutter_frames(count, params.strength, rng)
    share = GLITCH_SHARE + GLITCH_SHARE_SPAN * params.strength
    glitches = {
        k: frame_glitch(params.strength, size, rng)
        for k in range(count)
        if k == 0 or rng.random() < share
    }
    return GlitchWindow(tuple(frames), glitches)


def geq_filter(glitch: FrameGlitch, frame: int) -> str:
    """Return the geq filter that draws glitch on window frame frame."""
    slide = balanced_sum(
        [f"between(Y,{top},{bottom - 1})*({px})" for top, bottom, px in glitch.bands]
    )
    shift = f"X-({slide})"
    return (
        f"geq=r='r({shift}-({glitch.split}),Y)':g='g({shift},Y)'"
        f":b='b({shift}+({glitch.split}),Y)':enable='eq(n,{frame})'"
    )


def glitch_filters_of(window: GlitchWindow) -> list[str]:
    """Return the RGB filters that play window (stutter, then glitch
    frames)."""
    filters = []
    if list(window.frames) != list(range(len(window.frames))):
        filters.append(f"shuffleframes=mapping={'|'.join(map(str, window.frames))}")
    filters.append(RGB_FORMAT)
    filters += [geq_filter(g, k) for k, g in sorted(window.glitches.items())]
    return filters


def split_offsets(offset_px: float, angle_deg: float, width: int) -> tuple[int, int]:
    """Return red's rgbashift (h, v) px for an RGB split of offset_px (of a
    REFERENCE_WIDTH frame) at angle_deg in a frame width px wide."""
    offset = offset_px * width / REFERENCE_WIDTH
    angle = math.radians(angle_deg)
    h, v = round(offset * math.cos(angle)), round(-offset * math.sin(angle))
    if h == 0 and v == 0:
        if abs(math.cos(angle)) >= abs(math.sin(angle)):
            h = 1 if math.cos(angle) >= 0 else -1
        else:
            v = -1 if math.sin(angle) >= 0 else 1
    return h, v


def rgb_split_filters(item: RgbSplitItem, width: int) -> list[str]:
    """Return the RGB filters of the rgb_split item in a frame width px
    wide."""
    h, v = split_offsets(item.params.offset_px, item.params.angle_deg, width)
    return [RGB_FORMAT, f"rgbashift=rh={h}:rv={v}:bh={-h}:bv={-v}"]


def window_filter(
    index: int, item: TypedEdlItem, fps: int, filters: Sequence[str]
) -> str | None:
    """Return the filter that draws the RGB filters on the window of item
    only (window.over_window); None when the window holds no frame."""
    first, end = frame_range(item.t_start, item.t_end, fps)
    if end <= first:
        return None
    return over_window(
        f"pe_glitch{index}",
        first,
        end,
        fps,
        lambda source: f"{window_frames(source, first, end)},{','.join(filters)}",
    )


def item_filters(item: TypedEdlItem, canvas: Canvas) -> list[str]:
    """Return the RGB filters of item (glitch, rgb_split or glitch
    transition) on canvas; empty for any other item."""
    if isinstance(item, RgbSplitItem):
        return rgb_split_filters(item, canvas.size[0])
    if isinstance(item, GlitchItem):
        params = item.params
    elif isinstance(item, TransitionItem) and item.params.type == "glitch":
        params = TRANSITION_GLITCH.model_copy(update={"seed": item.id})
    else:
        return []
    first, end = frame_range(item.t_start, item.t_end, canvas.fps)
    return glitch_filters_of(glitch_window(params, first, end - first, canvas.size))


def glitch_filters(items: Sequence[TypedEdlItem], canvas: Canvas) -> list[str]:
    """Return the filters that draw the glitch and rgb_split items and the
    glitch frames of glitch transitions among items on canvas, in time
    order."""
    filters: list[str] = []
    for item in sorted(items, key=lambda i: (i.t_start, i.id)):
        drawn = item_filters(item, canvas)
        found = window_filter(len(filters), item, canvas.fps, drawn) if drawn else None
        if found is not None:
            filters.append(found)
    return filters
