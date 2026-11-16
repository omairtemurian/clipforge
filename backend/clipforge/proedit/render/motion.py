"""Zoom and pan of a Pro Edit render (SPEC-v3 3.3): the zoom track's
zoom_punch, zoom_push, zoom_out_reveal and pan items, drawn on the framed
clip after its freeze frames and before its grade (graph.STAGES), so a
vignette and grain stay put on the zoomed picture.

Planned motion on frame k of the count frames of an item's window
(timing.frame_range), with p = k / (count - 1) (1 for a single frame) and
the item's easing curve (easing.ease):
- zoom_punch: to params.scale instantly (ease_frames 0) or over its first
  ease_frames frames (frame k at ease((k + 1) / ease_frames)), from scale 1
  or, right after another zoom item, from that item's last scale; it snaps
  back at t_end.
- zoom_push and zoom_out_reveal: scale_from to scale_to over the window.
- pan: params.scale throughout, the window's center moving from (from_x,
  from_y) to (to_x, to_y).
Other frames are not zoomed. Zooms center on the subject's face
(canvas.faces; center "face"): its center averaged over SMOOTH_S seconds
each side, so detection jitter does not shake the picture; the frame's
center with center "frame" or when no face is known in the window.

Face-safe crop: the subject's face stays inside the picture with
FACE_MARGIN of the window's side around it.
- An item whose peak scale (back/elastic overshoot included) would not fit
  a face of its window with its margins is toned down: its zoom (scale - 1)
  is multiplied by the share that fits, keeping its curve. No scale goes
  below 1 (an out-reveal eased with back would undershoot).
- Each frame's window center moves the least that keeps the face and its
  margins inside the window, then the window inside the frame (where the
  face touches the frame's edge, it keeps the edge but not the margin).

Each frame then becomes whole pixels (Crop): the frame scaled to an even
width x height (at least its size), cut back to its size at an even (x, y)
inside it (crop rounds yuv420p offsets to even ones). The filters are
pipeline/zoom_graph's: `scale` with eval=frame, `crop`, setsar=1; their
expressions hold those numbers as steps of t, each change half a frame
before its frame (as timing.frame_window), summed balanced
(layout_parts.balanced_sum) so they never nest deep. They read t, not n:
scale's n runs one frame ahead (ffmpeg 9.0.2, docs/decisions.md).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from clipforge.models import EdlKind
from clipforge.pipeline.layout_parts import balanced_sum
from clipforge.proedit.edl import (
    PanItem,
    TypedEdlItem,
    ZoomOutRevealItem,
    ZoomPunchItem,
    ZoomPushItem,
)
from clipforge.proedit.render.canvas import Box, Camera, Canvas
from clipforge.proedit.render.easing import ease
from clipforge.proedit.render.timing import frame_range

MotionItem = ZoomPunchItem | ZoomPushItem | ZoomOutRevealItem | PanItem
MOTION_KINDS: frozenset[EdlKind] = frozenset(
    {"zoom_punch", "zoom_push", "zoom_out_reveal", "pan"}
)
FACE_MARGIN = 0.03
SMOOTH_S = 0.25
CENTER = (0.5, 0.5)
TIME_DECIMALS = 6


@dataclass(frozen=True)
class Crop:
    """A Camera in pixels: the frame scaled to width x height, then cut
    back to its own size from (x, y) of the scaled frame."""

    width: int
    height: int
    x: int
    y: int


def motion_items(items: Sequence[TypedEdlItem]) -> list[MotionItem]:
    """Return the zoom and pan items of items, in time order."""
    found = [
        item
        for item in items
        if isinstance(item, ZoomPunchItem | ZoomPushItem | ZoomOutRevealItem | PanItem)
    ]
    return sorted(found, key=lambda item: (item.t_start, item.id))


def planned(
    item: MotionItem, k: int, count: int, start_scale: float
) -> tuple[float, tuple[float, float] | None]:
    """Return the planned scale of frame k of the count frames of item's
    window (module docstring; a punch starts from start_scale) and, for a
    pan, its window's center (None for zooms)."""
    p = k / (count - 1) if count > 1 else 1.0
    if isinstance(item, ZoomPunchItem):
        frames = item.params.ease_frames
        share = ease(item.params.ease, (k + 1) / frames) if k < frames else 1.0
        return start_scale + (item.params.scale - start_scale) * share, None
    if isinstance(item, PanItem):
        share = ease(item.params.ease, p)
        x = item.params.from_x + (item.params.to_x - item.params.from_x) * share
        y = item.params.from_y + (item.params.to_y - item.params.from_y) * share
        return item.params.scale, (x, y)
    params = item.params
    share = ease(params.ease, p)
    return params.scale_from + (params.scale_to - params.scale_from) * share, None


def fitted(scales: Sequence[float], faces: Sequence[Box | None]) -> list[float]:
    """Return scales toned down so that the largest fits each face of faces
    with its margins (module docstring), none below 1."""
    fit = min(
        ((1 - 2 * FACE_MARGIN) / max(f.width, f.height) for f in faces if f),
        default=math.inf,
    )
    peak = max(scales, default=1.0)
    if peak > fit and peak > 1:
        share = max(fit - 1, 0.0) / (peak - 1)
        scales = [1 + (scale - 1) * share for scale in scales]
    return [max(scale, 1.0) for scale in scales]


def face_centers(
    faces: Sequence[Box | None], radius: int
) -> list[tuple[float, float]] | None:
    """Return the center of the faces within radius frames of each frame,
    averaged (the nearest face's where none is that close); None if faces
    holds no face."""
    known = [i for i, face in enumerate(faces) if face is not None]
    if not known:
        return None
    centers = []
    for index in range(len(faces)):
        near = [
            face.center
            for face in faces[max(index - radius, 0) : index + radius + 1]
            if face is not None
        ]
        if not near:
            closest = faces[min(known, key=lambda i: abs(i - index))]
            near = [closest.center] if closest else [CENTER]
        centers.append(
            (sum(x for x, _ in near) / len(near), sum(y for _, y in near) / len(near))
        )
    return centers


def safe_axis(target: float, scale: float, face: tuple[float, float] | None) -> float:
    """Return the window center on one axis nearest target that keeps face
    (its low and high edge, or None) and its margins inside the window of
    1 / scale, then the window inside the frame."""
    half = 0.5 / scale
    if face is not None:
        low, high = face
        margin = FACE_MARGIN / scale
        least, most = high - half + margin, low + half - margin
        if least > most:
            least = most = (least + most) / 2
        target = min(max(target, least), most)
    return min(max(target, half), 1 - half)


def item_cameras(
    item: MotionItem, canvas: Canvas, start_scale: float
) -> dict[int, Camera]:
    """Return the camera of each frame of item's window (module
    docstring); a punch starts from start_scale."""
    first, end = frame_range(item.t_start, item.t_end, canvas.fps)
    count = end - first
    if count <= 0:
        return {}
    plans = [planned(item, k, count, start_scale) for k in range(count)]
    faces = [canvas.face(frame) for frame in range(first, end)]
    scales = fitted([scale for scale, _ in plans], faces)
    centered = not isinstance(item, PanItem) and item.params.center == "face"
    smoothed = face_centers(faces, round(SMOOTH_S * canvas.fps)) if centered else None
    cameras = {}
    for k, (scale, (_, pan), face) in enumerate(zip(scales, plans, faces, strict=True)):
        x, y = pan or (smoothed[k] if smoothed else CENTER)
        cameras[first + k] = Camera(
            scale=scale,
            x=safe_axis(x, scale, (face.left, face.right) if face else None),
            y=safe_axis(y, scale, (face.top, face.bottom) if face else None),
        )
    return cameras


def cameras_of(items: Sequence[TypedEdlItem], canvas: Canvas) -> dict[int, Camera]:
    """Return the camera of each frame that a zoom or pan item of items
    moves, by frame number."""
    cameras: dict[int, Camera] = {}
    for item in motion_items(items):
        first, _ = frame_range(item.t_start, item.t_end, canvas.fps)
        before = cameras.get(first - 1)
        cameras.update(item_cameras(item, canvas, before.scale if before else 1.0))
    return cameras


def crop_of(camera: Camera, size: tuple[int, int]) -> Crop:
    """Return camera's view of a size (width, height, even) frame in whole
    pixels (module docstring)."""
    width, height = size
    scaled_w = max(_even_floor(width * camera.scale), width)
    scaled_h = max(_even_floor(height * camera.scale), height)
    x = min(max(_even_round(camera.x * scaled_w - width / 2), 0), scaled_w - width)
    y = min(max(_even_round(camera.y * scaled_h - height / 2), 0), scaled_h - height)
    return Crop(scaled_w, scaled_h, x, y)


def crops_of(items: Sequence[TypedEdlItem], canvas: Canvas) -> list[Crop]:
    """Return the crop of each frame from the first through the one after
    the last that a zoom or pan item moves; [] if none does."""
    return camera_crops(cameras_of(items, canvas), canvas.size)


def camera_crops(cameras: dict[int, Camera], size: tuple[int, int]) -> list[Crop]:
    """Return the crop of each frame of a size frame from the first through
    the one after the last that cameras (by frame number) move; frames
    without a camera are not moved. [] if cameras is empty."""
    if not cameras:
        return []
    width, height = size
    still = Crop(width, height, 0, 0)
    return [
        crop_of(cameras[frame], size) if frame in cameras else still
        for frame in range(max(cameras) + 2)
    ]


def steps(values: Sequence[int], fps: int) -> str:
    """Return the expression in t that is values[n] on frame n (at fps) and
    values[-1] after the last."""
    terms = [str(values[0])]
    for frame in range(1, len(values)):
        change = values[frame] - values[frame - 1]
        if change:
            at = round((frame - 0.5) / fps, TIME_DECIMALS)
            terms.append(f"{change}*gte(t,{at:.{TIME_DECIMALS}f})")
    return balanced_sum(terms)


def motion_filters(items: Sequence[TypedEdlItem], canvas: Canvas) -> list[str]:
    """Return the filters that zoom and pan canvas's frames as the zoom and
    pan items of items say (module docstring); [] if there are none."""
    return crop_filters(crops_of(items, canvas), canvas)


def crop_filters(crops: Sequence[Crop], canvas: Canvas) -> list[str]:
    """Return the filters that show crops[n] on frame n of canvas's frames
    (the last crop after them); [] if crops is empty."""
    if not crops:
        return []
    width, height = canvas.size
    fps = canvas.fps
    scaled_w = steps([crop.width for crop in crops], fps)
    scaled_h = steps([crop.height for crop in crops], fps)
    x = steps([crop.x for crop in crops], fps)
    y = steps([crop.y for crop in crops], fps)
    return [
        f"scale=w='{scaled_w}':h='{scaled_h}':eval=frame",
        f"crop=w={width}:h={height}:x='{x}':y='{y}'",
        "setsar=1",
    ]


def _even_floor(value: float) -> int:
    """Return value rounded down to an even number (float noise ignored)."""
    return 2 * math.floor(round(value, TIME_DECIMALS) / 2)


def _even_round(value: float) -> int:
    """Return value rounded to the nearest even number."""
    return 2 * round(value / 2)
