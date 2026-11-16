"""The zoom of a clip's framed frames (TASK-23 auto zoom), as an ffmpeg
filter chain that render_graph puts between the layout and the cuts.

The zoom keyframes (models.ZoomKeyframe, from pipeline/auto_zoom) give the
scale at source times; between them it moves linearly (layout_parts.ramp_expr,
an expression in t, the seconds since the clip's start). Each frame is
scaled up by its scale, to even sizes (scale with eval=frame, which
evaluates its size for each frame), then cropped back to the output size
around the subject: the center of the largest face of the fill window's
nearest crop keyframe, or the frame's center in the other layouts or with
no face. A clip framed scene by scene takes the subject from the plan and
layout of the scene that holds each keyframe's time. The crop window is
clamped inside the scaled frame, so a face near an edge stays in frame and
the frame is never padded.

crop's x and y are evaluated for each frame too, but its iw and ih are the
size it was configured with, not the size of a frame scaled for the zoom;
so the scaled size is written out again in the crop's expressions.
"""

from bisect import bisect_left
from collections.abc import Sequence

from clipforge.models import CropPlan, Layout, ZoomKeyframe
from clipforge.pipeline.layout_parts import ramp_expr, zoom_offset, zoomed_side
from clipforge.pipeline.scene_graph import ScenePart


def subject_center(plan: CropPlan, layout: Layout, time: float) -> tuple[float, float]:
    """Return where the subject is at time seconds of the source, as
    fractions (x, y) of the framed frame's width and height, clamped to
    [0, 1]: the center of the subject (the face marked subject, else the
    largest) of plan's crop keyframe nearest to time in the fill layout;
    (0.5, 0.5) otherwise."""
    keyframes = plan.keyframes
    if layout != "fill" or not keyframes:
        return 0.5, 0.5
    index = bisect_left([k.t for k in keyframes], time)
    near = keyframes[max(index - 1, 0) : index + 1]
    keyframe = min(near, key=lambda k: abs(k.t - time))
    if not keyframe.faces:
        return 0.5, 0.5
    face = next((f for f in keyframe.faces if f.subject), keyframe.faces[0])
    top = plan.y if keyframe.y is None else keyframe.y
    x = (face.x + face.width / 2 - keyframe.x) / plan.width
    y = (face.y + face.height / 2 - top) / plan.height
    return min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)


def framing_at(
    scenes: Sequence[ScenePart], plan: CropPlan, layout: Layout, time: float
) -> tuple[CropPlan, Layout]:
    """Return the plan and layout of the scene of scenes that holds time
    seconds of the source (the first before the first scene, the last
    after the last one); plan and layout if there are no scenes."""
    if not scenes:
        return plan, layout
    index = bisect_left([part.end for part in scenes], time, hi=len(scenes) - 1)
    if scenes[index].end == time and index + 1 < len(scenes):
        index += 1
    return scenes[index].plan, scenes[index].layout


def zoom_filter(
    keyframes: Sequence[ZoomKeyframe],
    plan: CropPlan,
    layout: Layout,
    start: float,
    size: tuple[int, int],
    scenes: Sequence[ScenePart] = (),
) -> str:
    """Return the filters that zoom size (width, height) frames of the clip
    of plan, framed in layout (or scene by scene as scenes say, if set), that
    starts at start seconds, as keyframes say (module docstring); "" if no
    keyframe zooms."""
    if all(keyframe.scale == 1 for keyframe in keyframes):
        return ""
    width, height = size
    times = [keyframe.t for keyframe in keyframes]
    scale = ramp_expr(times, [keyframe.scale for keyframe in keyframes], start, ".4f")
    centers = [
        subject_center(*framing_at(scenes, plan, layout, time), time) for time in times
    ]
    center_x = ramp_expr(times, [width * x for x, _ in centers], start, ".1f")
    center_y = ramp_expr(times, [height * y for _, y in centers], start, ".1f")
    scaled_w, scaled_h = zoomed_side(width, scale), zoomed_side(height, scale)
    x = zoom_offset(center_x, scaled_w, width)
    y = zoom_offset(center_y, scaled_h, height)
    return (
        f"scale=w='{scaled_w}':h='{scaled_h}':eval=frame,"
        f"crop=w={width}:h={height}:x='{x}':y='{y}',setsar=1"
    )
