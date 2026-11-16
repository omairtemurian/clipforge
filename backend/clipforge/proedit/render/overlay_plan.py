"""Where an overlay item of a Pro Edit render sits on each frame of its window
(SPEC-v3 3.3 motion): its anchor, size and animation (overlay.py draws it).

Anchors (params.anchor):
- screen: the overlay is centered at (x, y), fractions of the frame, and is
  scale times the frame's width wide.
- face: on each frame, the subject's face (canvas.faces, face_path) as it
  shows after the zoom stage's camera of that frame (seen: zooms, pans and
  shakes move and scale it); the overlay is centered at (x, y) of that box
  (fractions of its width and height: 0.5, 0.5 is the face's center) and
  is scale times the box's width wide, so it follows and grows with the
  face.
- object: the same with the tracked object (canvas.objects:
  pipeline/object_tracking's box).
A frame of the window without a box takes the nearest frame's box of the
window; when no frame of the window has one, the overlay is placed as a
screen overlay.

Animation (params.animation), on frame k (from 0) of the count frames of
the window, with intro = INTRO_S seconds of frames (at least 1):
- none: as placed.
- fade: opacity (k + 1) / intro in, (count - k) / intro out, at most 1.
- pop: size times ease("back", (k + 1) / intro): grows from nothing past
  its size and settles.
- bounce: size times ease("elastic", (k + 1) / bounce) over BOUNCE_S
  seconds: springs in.
- slide: rises into place from SLIDE_SHARE of the frame's height below it,
  ease("ease_in_out", (k + 1) / intro).
After t_end the overlay is gone.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from clipforge.proedit.edl import OverlayItem
from clipforge.proedit.edl_params import PopAnimation
from clipforge.proedit.render.canvas import Box, Camera, Canvas
from clipforge.proedit.render.easing import ease
from clipforge.proedit.render.motion import crop_of
from clipforge.proedit.render.timing import frame_range

INTRO_S = 0.2
BOUNCE_S = 0.4
SLIDE_SHARE = 0.15


@dataclass(frozen=True)
class Placement:
    """The overlay on one frame: centered at (x, y) pixels of the frame,
    width pixels wide (its height by its aspect), at opacity alpha (0..1)."""

    x: float
    y: float
    width: float
    alpha: float


def seen(box: Box, camera: Camera | None, size: tuple[int, int]) -> Box:
    """Return box (fractions of a size frame) where it shows after camera
    (None: the frame is not moved), in the zoom stage's whole pixels
    (motion.crop_of)."""
    if camera is None:
        return box
    crop = crop_of(camera, size)
    width, height = size
    return Box(
        left=(box.left * crop.width - crop.x) / width,
        top=(box.top * crop.height - crop.y) / height,
        right=(box.right * crop.width - crop.x) / width,
        bottom=(box.bottom * crop.height - crop.y) / height,
    )


def anchor_boxes(item: OverlayItem, canvas: Canvas) -> list[Box] | None:
    """Return the box that item is anchored to on each frame of its window,
    as seen after the zoom stage (module docstring), or None for a screen
    anchor or when no frame of the window has a box."""
    anchor = item.params.anchor
    if anchor == "screen":
        return None
    first, end = frame_range(item.t_start, item.t_end, canvas.fps)
    find = canvas.face if anchor == "face" else canvas.object
    found = [find(frame) for frame in range(first, end)]
    known = [k for k, box in enumerate(found) if box is not None]
    if not known:
        return None
    boxes = []
    for k, box in enumerate(found):
        if box is None:
            box = found[min(known, key=lambda j: (abs(j - k), j))]
        assert box is not None
        boxes.append(seen(box, canvas.cameras.get(first + k), canvas.size))
    return boxes


def animated(
    animation: PopAnimation, k: int, count: int, fps: int
) -> tuple[float, float, float]:
    """Return the size factor, opacity and drop (a share of the frame's
    height, downward) of frame k of count frames at fps (module
    docstring)."""
    intro = max(round(INTRO_S * fps), 1)
    p = (k + 1) / intro
    if animation == "fade":
        return 1.0, min(1.0, p, (count - k) / intro), 0.0
    if animation == "pop":
        return max(ease("back", p), 0.0), 1.0, 0.0
    if animation == "bounce":
        bounce = max(round(BOUNCE_S * fps), 1)
        return max(ease("elastic", (k + 1) / bounce), 0.0), 1.0, 0.0
    if animation == "slide":
        return 1.0, 1.0, SLIDE_SHARE * (1 - ease("ease_in_out", p))
    return 1.0, 1.0, 0.0


def placements(item: OverlayItem, canvas: Canvas) -> list[Placement]:
    """Return item's placement on each frame of its window on canvas
    (module docstring)."""
    first, end = frame_range(item.t_start, item.t_end, canvas.fps)
    count = end - first
    width, height = canvas.size
    params = item.params
    boxes: Sequence[Box] | None = anchor_boxes(item, canvas)
    found = []
    for k in range(count):
        if boxes is None:
            x, y, wide = params.x * width, params.y * height, params.scale * width
        else:
            box = boxes[k]
            x = (box.left + params.x * box.width) * width
            y = (box.top + params.y * box.height) * height
            wide = params.scale * box.width * width
        grow, alpha, drop = animated(params.animation, k, count, canvas.fps)
        found.append(Placement(x, y + drop * height, wide * grow, alpha))
    return found
