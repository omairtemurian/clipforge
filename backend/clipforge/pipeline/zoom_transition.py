"""The zoom between a fill scene and a zoomed-out one (TASK-198): instead of
a hard cut, the first (or last) seconds of the zoomed-out part (fit or
square_blur, pipeline/layouts) zoom out from (or in to) the fill window.

A zoomed-out frame shows the source's front region (the whole frame for
fit, the square for square_blur, layout_parts.square_place) at k output
pixels per source pixel over its background. The fill window of the
neighbouring scene at the edge, a box of the source, is a rectangle of
that frame; zooming the frame by zoom (output size over the box's size
in output pixels) about the box's center shows exactly the fill frame. The
zoom eases (smoothstep) from that zoom to 1 over the ease's seconds, as
pipeline/zoom_graph does it: scale with eval=frame, then crop back to the
output size around the box's center, clamped inside the scaled frame.
"""

from dataclasses import dataclass

import numpy as np

from clipforge.models import CropPlan, Layout
from clipforge.pipeline.layout_parts import (
    even,
    square_centers,
    square_place,
    zoom_offset,
    zoomed_side,
)


@dataclass(frozen=True)
class Ease:
    """A zoom of seconds between the zoomed-out part and the fill window box
    (x, y, width, height source pixels) of its neighbour at their edge, in a
    frame (width, height) source."""

    box: tuple[float, float, float, float]
    frame: tuple[int, int]
    seconds: float


def front_geometry(
    layout: Layout,
    plan: CropPlan,
    t: float,
    frame: tuple[int, int],
    size: tuple[int, int],
) -> tuple[float, float, float, float, float]:
    """Return (k, source x, source y, output x, output y) of the front
    region of layout (fit or square_blur) with plan at t seconds of a frame
    source in a size output: k output pixels per source pixel, and the
    region's top-left corner in source and in output pixels."""
    frame_width, frame_height = frame
    width, height = size
    if layout == "square_blur":
        side = min(frame)
        times = [keyframe.t for keyframe in plan.keyframes]
        center = (
            float(np.interp(t, times, square_centers(plan)))
            if plan.keyframes
            else frame_width / 2
        )
        source_x = min(max(even(round(center - side / 2)), 0), frame_width - side)
        source_y = even((frame_height - side) // 2)
        left, top = square_place(size)
        return min(size) / side, source_x, source_y, left, top
    k = min(width / frame_width, height / frame_height)
    return k, 0, 0, (width - frame_width * k) / 2, (height - frame_height * k) / 2


def ease_target(
    ease: Ease, layout: Layout, plan: CropPlan, t: float, size: tuple[int, int]
) -> tuple[float, float, float]:
    """Return (zoom, center x, center y in output pixels) that shows ease's
    fill box in a size output of layout with plan at t seconds."""
    k, source_x, source_y, left, top = front_geometry(layout, plan, t, ease.frame, size)
    x, y, box_width, box_height = ease.box
    center_x = left + (x + box_width / 2 - source_x) * k
    center_y = top + (y + box_height / 2 - source_y) * k
    zoom = max(1.0, size[0] / (box_width * k), size[1] / (box_height * k))
    return zoom, center_x, center_y


def transition_filter(
    layout: Layout,
    plan: CropPlan,
    span: tuple[float, float],
    eases: tuple[Ease | None, Ease | None],
    size: tuple[int, int],
) -> str:
    """Return the filters that ease the frames of a part of span (start, end
    source seconds, its frames' t counting from 0) in layout with plan, as
    size frames, in from eases[0] at its start and out to eases[1] at its
    end (module docstring); "" if neither is set."""
    start, end = span
    duration = end - start
    zoom_terms, centers_x, centers_y = ["1"], [], []
    for ease, at_start in ((eases[0], True), (eases[1], False)):
        if ease is None:
            continue
        seconds = max(min(ease.seconds, duration / 2), 1e-3)
        zoom, center_x, center_y = ease_target(
            ease, layout, plan, start if at_start else end, size
        )
        ramp = (
            f"clip(t/{seconds:.3f},0,1)"
            if at_start
            else f"clip(({duration:.3f}-t)/{seconds:.3f},0,1)"
        )
        weight = f"(1-({ramp})*({ramp})*(3-2*({ramp})))"
        zoom_terms.append(f"{zoom - 1:.4f}*{weight}")
        centers_x.append((at_start, center_x))
        centers_y.append((at_start, center_y))
    if len(zoom_terms) == 1:
        return ""
    width, height = size
    zoom_expr = "+".join(zoom_terms)
    scaled_w, scaled_h = zoomed_side(width, zoom_expr), zoomed_side(height, zoom_expr)
    x = zoom_offset(_center(centers_x, duration), scaled_w, width)
    y = zoom_offset(_center(centers_y, duration), scaled_h, height)
    return (
        f"scale=w='{scaled_w}':h='{scaled_h}':eval=frame,"
        f"crop=w={width}:h={height}:x='{x}':y='{y}',setsar=1"
    )


def _center(centers: list[tuple[bool, float]], duration: float) -> str:
    """Return the expression of the zoom's center: the start ease's in the
    first half of the part, the end ease's in the second."""
    if len(centers) == 1:
        return f"{centers[0][1]:.1f}"
    (_, first), (_, last) = centers
    return f"if(lt(t,{duration / 2:.3f}),{first:.1f},{last:.1f})"
