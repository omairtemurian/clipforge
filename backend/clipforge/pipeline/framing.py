"""Framing (the editor's player toolbar and crop tool) on top of a crop plan.

The crop plan that reframe wrote for a clip (crop_<clip_id>.json) is framed
for the project's aspect and follows the subject. The editor changes it
with the clip's framing (models.Framing) and crop offset; framed_plan is
the plan that render and the preview use:

1. the plan for the clip's aspect, if it has its own (reframe.replan, from
   the faces the plan holds), with the grid and pip windows added if the
   clip uses those layouts and the plan predates them
   (layout_windows.add_layout_windows), and the facecam box if it uses the
   screenshare or gameplay layout and the plan has none
   (layout_windows.add_facecam);
2. its fill window shifted by the crop offset (layouts.nudge_plan);
3. the crop tool's window size and points (apply_crop_tool);
4. the fit layout's background, and the facecam box the user drew, if any.

The crop tool's window has the planned window's shape at scale times its
size. With the tracker on, the window follows the planned path, moved by a
shift that makes its center the point's at each point's time (shifts are
interpolated between points and held before the first and after the last);
with it off, the window's center is the points' (interpolated the same
way), or the planned window's at its first keyframe if there are no
points. The window's top is the points' center height, else the plan's.
Each keyframe's window is then kept inside the frame, on even pixels.
"""

from bisect import bisect_right
from collections.abc import Sequence
from pathlib import Path

from clipforge.models import (
    Aspect,
    Clip,
    CropKeyframe,
    CropPlan,
    CropTrack,
    Framing,
    Layout,
)
from clipforge.pipeline.facecam import FACECAM_LAYOUTS
from clipforge.pipeline.layout_windows import add_facecam, add_layout_windows
from clipforge.pipeline.layouts import WINDOW_LAYOUTS, nudge_plan
from clipforge.pipeline.reframe import crop_path, replan, scene_cuts
from clipforge.pipeline.step import load_json, load_meta


def interpolate(times: Sequence[float], values: Sequence[float], t: float) -> float:
    """Return the value at t of the line through (times[k], values[k]),
    sorted by time, held before the first and after the last; 0 if there
    are no values."""
    if not values:
        return 0.0
    k = bisect_right(times, t)
    if k == 0:
        return values[0]
    if k == len(times):
        return values[-1]
    t0, t1, v0, v1 = times[k - 1], times[k], values[k - 1], values[k]
    return v0 + (v1 - v0) * (t - t0) / (t1 - t0) if t1 > t0 else v1


def uses_crop_tool(framing: Framing) -> bool:
    """Return True if framing changes the fill window: points, a smaller
    window or the tracker off."""
    return bool(framing.points) or framing.scale < 1 or not framing.tracker


def apply_crop_tool(
    plan: CropPlan, framing: Framing, frame_size: tuple[int, int]
) -> CropPlan:
    """Return plan with its fill window sized and placed by framing's crop
    tool (see the module docstring) in a frame_size (width, height) source;
    plan itself if framing does not use the crop tool."""
    if not uses_crop_tool(framing):
        return plan
    frame_width, frame_height = frame_size
    width = max(2, even_pixels(round(plan.width * framing.scale)))
    height = max(2, even_pixels(round(plan.height * framing.scale)))
    planned = plan.keyframes or [CropKeyframe(t=plan.start, x=0, faces=[])]
    times = [keyframe.t for keyframe in planned]
    if plan.keyframes:
        tracked = [
            min(max(keyframe.x, 0), frame_width - plan.width) + plan.width / 2
            for keyframe in planned
        ]
    else:
        tracked = [frame_width / 2]
    points = sorted(framing.points, key=lambda point: point.t)
    point_times = [point.t for point in points]
    point_xs = [point.x * frame_width for point in points]
    if framing.tracker:
        shifts = [
            x - interpolate(times, tracked, point.t)
            for point, x in zip(points, point_xs, strict=True)
        ]
        centers = [
            center + interpolate(point_times, shifts, t)
            for t, center in zip(times, tracked, strict=True)
        ]
    elif points:
        centers = [interpolate(point_times, point_xs, t) for t in times]
    else:
        centers = [tracked[0]] * len(times)
    middle = plan.y + plan.height / 2
    point_ys = [point.y * frame_height for point in points]
    keyframes = [
        CropKeyframe(
            t=t,
            x=place_window(center, width, frame_width),
            y=place_window(
                interpolate(point_times, point_ys, t) if points else middle,
                height,
                frame_height,
            ),
            faces=keyframe.faces,
        )
        for t, center, keyframe in zip(times, centers, planned, strict=True)
    ]
    return plan.model_copy(
        update={"width": width, "height": height, "keyframes": keyframes}
    )


def framed_plan(work: Path, clip: Clip) -> CropPlan:
    """Return the crop plan that frames clip as the editor set it (see the
    module docstring), from the job work directory work.

    Raises StepError if the clip's crop plan is missing or not valid, or if
    meta.json (for the crop tool or another aspect) or signals.json (for
    another aspect) is, or either is when an older plan needs the windows
    of the grid or pip layout, or meta.json is when a plan without a
    facecam box is used in the screenshare or gameplay layout.
    """
    framing = clip.framing
    plan, frame_size = planned(work, clip, uses_crop_tool(framing))
    plan = nudge_plan(plan, clip.crop_offset)
    plan = apply_crop_tool(plan, framing, frame_size)
    facecam = framing.facecam or plan.facecam
    return plan.model_copy(
        update={"background": framing.background, "facecam": facecam}
    )


def planned(
    work: Path, clip: Clip, needs_frame: bool = True
) -> tuple[CropPlan, tuple[int, int]]:
    """Return the crop plan that reframe made for clip, in the clip's
    aspect (step 1 of the module docstring), and the source's frame size,
    from the job work directory work; the frame size is read only if the
    aspect differs from the plan's or needs_frame is set, else it is
    (0, 0). Raises StepError like framed_plan."""
    plan = load_json(crop_path(work, clip.id), CropPlan, "reframe")
    aspect = clip.framing.aspect or plan.aspect
    windows = uses_layouts(clip, WINDOW_LAYOUTS) and not plan.grid
    facecam = (
        uses_layouts(clip, FACECAM_LAYOUTS)
        and plan.facecam is None
        and clip.framing.facecam is None
    )
    reframing = aspect != plan.aspect or windows
    uses_frame = reframing or facecam or needs_frame
    frame_size = _frame_size(work) if uses_frame else (0, 0)
    cuts = scene_cuts(work) if reframing else []
    plan = replan(plan, aspect, frame_size, cuts)
    if windows:
        plan = add_layout_windows(plan, frame_size, cuts)
    if facecam:
        plan = add_facecam(plan, frame_size)
    return plan, frame_size


def uses_layouts(clip: Clip, layouts: Sequence[Layout]) -> bool:
    """Return True if clip, or one of its scenes, is in one of layouts."""
    used = [clip.layout, *(scene.layout for scene in clip.scene_reframes)]
    return any(layout in layouts for layout in used)


def crop_track(work: Path, clip_id: int, aspect: Aspect | None) -> CropTrack:
    """Return the fill window that reframe planned for clip clip_id in
    aspect (its plan's if None), with the plan's facecam box (found from
    its faces for an older plan), from the job work directory work. Raises
    StepError like framed_plan."""
    plan = load_json(crop_path(work, clip_id), CropPlan, "reframe")
    aspect = aspect or plan.aspect
    frame_width, frame_height = _frame_size(work)
    frame_size = (frame_width, frame_height)
    plan = replan(plan, aspect, frame_size, _cuts(work, plan, aspect))
    if plan.facecam is None:
        plan = add_facecam(plan, frame_size)
    return CropTrack(
        aspect=plan.aspect,
        frame_width=frame_width,
        frame_height=frame_height,
        width=plan.width,
        height=plan.height,
        y=plan.y,
        times=[keyframe.t for keyframe in plan.keyframes],
        xs=[keyframe.x for keyframe in plan.keyframes],
        facecam=plan.facecam,
    )


def _frame_size(work: Path) -> tuple[int, int]:
    """Return the (width, height) of the source of work (meta.json)."""
    meta = load_meta(work)
    return meta.width, meta.height


def _cuts(work: Path, plan: CropPlan, aspect: Aspect) -> list[float]:
    """Return the scene cuts of work if plan must be framed for another
    aspect (replan needs them), else none."""
    return scene_cuts(work) if aspect != plan.aspect else []


def place_window(center: float, size: int, limit: int) -> int:
    """Return the even start of a window of size centered at center, kept
    inside 0..limit."""
    start = even_pixels(round(center - size / 2))
    return max(0, min(start, even_pixels(limit - size)))


def even_pixels(value: int) -> int:
    """Round value down to an even number."""
    return value - value % 2
