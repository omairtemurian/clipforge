"""Overlays of a Pro Edit render (SPEC-v3 1.3, 3.3): the overlay track's
overlay items (procedural skull, skeleton, arrow, circle or emoji:
overlays/procedural.py), anchored to the screen, the subject's face or the
tracked object, animated (overlay_plan.py), drawn with their alpha on the
frames of their window only (graph.STAGES "overlay": after the grade, so
the graphic keeps its own colors, before glitches and flashes).

Each frame of an item's window is drawn in Python (Pillow): the asset's
sprite is drawn once at the window's largest width, turned by
rotation_deg (counterclockwise) and, per frame, scaled to its placement's
width (Lanczos), faded to its opacity and put at its place in whole
pixels. The frames are cut to the box that holds the item on every frame
(inside the frame, on even pixels, as yuv420p needs) and written as
FRAME_PATTERN PNG files (RGBA) to the overlay cache in the data directory,
in a folder named after the frames' contents (written once; the same plan
draws the same files).

Filters (ffmpeg 9.0.2, verified with `ffmpeg -h filter=movie|settb|
setpts|overlay` and test renders; docs/decisions.md): `movie` reads the
frames (`f=image2`), `settb` 1/fps and `setpts=N+first` time frame n of
the window at frame first + n of the clip, and `overlay` draws them at the
box's corner (`eof_action=pass`, `repeatlast=0`, timeline `enable` on the
window): frames outside the window pass through untouched, bit for bit.
MAIN_FORMAT keeps the picture under the overlay in limited range: left
free, ffmpeg's range negotiation takes the full range of the RGBA frames
and the render comes out yuvj420p.
"""

import hashlib
import json
import math
import os
import shutil
from collections.abc import Sequence
from dataclasses import astuple, dataclass
from pathlib import Path

from PIL import Image

from clipforge import config
from clipforge.ffmpeg import filter_value
from clipforge.models import EdlKind
from clipforge.proedit.edl import OverlayItem, TypedEdlItem
from clipforge.proedit.overlays.procedural import asset_problem, sprite
from clipforge.proedit.render.canvas import Canvas
from clipforge.proedit.render.overlay_plan import Placement, placements
from clipforge.proedit.render.timing import enable, frame_range

OVERLAY_KINDS: frozenset[EdlKind] = frozenset({"overlay"})
CACHE_DIRNAME = Path("proedit") / "overlays"
FRAME_PATTERN = "%05d.png"
# Raise when the drawings or the way frames are made change (cache key).
DRAWING_VERSION = 1
PNG_COMPRESSION = 1
MAIN_FORMAT = "format=pix_fmts=yuv420p:color_ranges=tv"


@dataclass(frozen=True)
class Spot:
    """The sprite on one frame in whole pixels: width x height at (left,
    top) of the frame, at opacity alpha; empty when it is too small or
    transparent to draw."""

    left: int
    top: int
    width: int
    height: int
    alpha: float

    @property
    def empty(self) -> bool:
        """Return whether the frame shows nothing of the sprite."""
        return self.width < 1 or self.height < 1 or self.alpha <= 0


@dataclass(frozen=True)
class Frames:
    """An item's frames: their files (FRAME_PATTERN in folder), each
    width x height pixels drawn at (x, y) of the clip's frame."""

    folder: Path
    x: int
    y: int
    width: int
    height: int


def overlay_items(items: Sequence[TypedEdlItem]) -> list[OverlayItem]:
    """Return the overlay items of items, in time order."""
    found = [item for item in items if isinstance(item, OverlayItem)]
    return sorted(found, key=lambda item: (item.t_start, item.id))


def overlay_problems(items: Sequence[TypedEdlItem]) -> list[str]:
    """Return why overlay items of items cannot be drawn (an unknown asset
    or an emoji the font lacks)."""
    problems = []
    for item in overlay_items(items):
        problem = asset_problem(item.params.asset)
        if problem:
            problems.append(f"item {item.id} (overlay): {problem}")
    return problems


def spots(base: Image.Image, peak: int, places: Sequence[Placement]) -> list[Spot]:
    """Return where base (the sprite drawn peak pixels wide, turned) shows on
    each frame of places."""
    found = []
    for place in places:
        share = place.width / peak
        width, height = round(base.width * share), round(base.height * share)
        left, top = round(place.x - width / 2), round(place.y - height / 2)
        found.append(Spot(left, top, width, height, round(place.alpha, 4)))
    return found


def bounds(found: Sequence[Spot], size: tuple[int, int]) -> tuple[int, ...] | None:
    """Return the box (left, top, right, bottom) on even pixels inside a size
    frame that holds every spot of found, or None if none shows."""
    shown = [spot for spot in found if not spot.empty]
    if not shown:
        return None
    width, height = size
    left = max(min(spot.left for spot in shown), 0) // 2 * 2
    top = max(min(spot.top for spot in shown), 0) // 2 * 2
    right = min(math.ceil(max(s.left + s.width for s in shown) / 2) * 2, width)
    bottom = min(math.ceil(max(s.top + s.height for s in shown) / 2) * 2, height)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def item_frames(item: OverlayItem, canvas: Canvas) -> Frames | None:
    """Return item's frames on canvas (module docstring), written to the
    overlay cache; None if it shows on no frame."""
    places = placements(item, canvas)
    peak = math.ceil(max((place.width for place in places), default=0.0))
    if peak < 1:
        return None
    params = item.params
    base = sprite(params.asset, peak)
    if params.rotation_deg:
        base = base.rotate(
            params.rotation_deg, resample=Image.Resampling.BICUBIC, expand=True
        )
    found = spots(base, peak, places)
    box = bounds(found, canvas.size)
    if box is None:
        return None
    left, top, right, bottom = box
    key = json.dumps(
        [DRAWING_VERSION, params.asset, params.rotation_deg, peak, box]
        + [astuple(spot) for spot in found]
    )
    folder = config.settings.data_dir / CACHE_DIRNAME / _digest(key)
    if not folder.exists():
        _write_frames(folder, base, found, box)
    return Frames(folder, left, top, right - left, bottom - top)


def _write_frames(
    folder: Path, base: Image.Image, found: Sequence[Spot], box: tuple[int, ...]
) -> None:
    """Write a frame of the box for each spot of found into folder, at once
    (a partial folder is never seen)."""
    left, top, right, bottom = box
    partial = folder.with_name(f"{folder.name}.{os.getpid()}.tmp")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    scaled: dict[tuple[int, int, float], Image.Image] = {}
    for index, spot in enumerate(found):
        frame = Image.new("RGBA", (right - left, bottom - top))
        if not spot.empty:
            key = (spot.width, spot.height, spot.alpha)
            if key not in scaled:
                scaled[key] = _faded(base, spot)
            frame.paste(scaled[key], (spot.left - left, spot.top - top))
        frame.save(partial / (FRAME_PATTERN % index), compress_level=PNG_COMPRESSION)
    try:
        os.replace(partial, folder)
    except OSError:
        shutil.rmtree(partial, ignore_errors=True)
        if not folder.exists():
            raise


def _faded(base: Image.Image, spot: Spot) -> Image.Image:
    """Return base scaled to spot's size at spot's opacity."""
    image = base.resize((spot.width, spot.height), Image.Resampling.LANCZOS)
    if spot.alpha < 1:
        alpha = image.getchannel("A").point(lambda value: round(value * spot.alpha))
        image.putalpha(alpha)
    return image


def overlay_filter(item: OverlayItem, frames: Frames, fps: int) -> str:
    """Return the filter that draws frames on item's window (module
    docstring), as one link of a filter chain."""
    first, _ = frame_range(item.t_start, item.t_end, fps)
    main, drawn = f"[ov{item.id}main]", f"[ov{item.id}img]"
    pattern = filter_value(str((frames.folder / FRAME_PATTERN).absolute()))
    return (
        f"{MAIN_FORMAT}{main};movie=filename={pattern}:f=image2,settb=expr=1/{fps},"
        f"setpts=N+{first},format=rgba{drawn};{main}{drawn}overlay=x={frames.x}:"
        f"y={frames.y}:eof_action=pass:repeatlast=0:"
        f"{enable(item.t_start, item.t_end, fps)}"
    )


def overlay_filters(items: Sequence[TypedEdlItem], canvas: Canvas) -> list[str]:
    """Return the filters that draw the overlay items of items on canvas's
    frames (module docstring); [] if none shows."""
    filters = []
    for item in overlay_items(items):
        frames = item_frames(item, canvas)
        if frames is not None:
            filters.append(overlay_filter(item, frames, canvas.fps))
    return filters


def _digest(text: str) -> str:
    """Return a short name for text's contents."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]
