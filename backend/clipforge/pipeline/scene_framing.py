"""The crop plans of a clip's scenes (STEERING item 7), which render frames
scene by scene (pipeline/scene_graph).

A scene in auto mode, or in a layout other than fill, is framed with the
clip's framed plan (framing.framed_plan). A fill scene in track or fixed
mode has a window of the planned window's shape (framing.planned) at the
scene's scale times its size, whose center is at the scene's crop
keyframes: linear between them, held before the first and after the last
(the crop expressions of pipeline/layout_parts ramp between keyframes); a fixed
scene without keyframes holds the framed plan's window of its start. Each
window is kept inside the frame, on even pixels.

Neighbouring scenes that are framed alike (both auto, or both fit or both
split, in one layout) are one part, so a clip whose scenes all frame it as
the clip does is one part. A zoomed-out part (fit or square_blur) next to a
fill part zooms from or to that part's fill window over
config.zoom_out.transition_s (add_eases, pipeline/zoom_transition), unless
a scene cut of the source is at their edge (within CUT_TOLERANCE_S).
"""

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from clipforge import config
from clipforge.models import Clip, CropKeyframe, CropPlan, SceneReframe
from clipforge.pipeline.framing import (
    even_pixels,
    interpolate,
    place_window,
    planned,
)
from clipforge.pipeline.layout_auto import ZOOM_OUT_LAYOUTS
from clipforge.pipeline.reframe import scene_cuts
from clipforge.pipeline.scene_graph import ScenePart
from clipforge.pipeline.step import SIGNALS, load_meta
from clipforge.pipeline.zoom_transition import Ease

# A scene cut this close (seconds) to a part's edge makes it a hard cut.
CUT_TOLERANCE_S = 0.05


def scene_parts(work: Path, clip: Clip, framed: CropPlan) -> list[ScenePart]:
    """Return the parts of clip, framed scene by scene as its scenes say
    (module docstring), from the job work directory work, where framed is
    the clip's framed plan; none if the clip has no scenes. Raises
    StepError like framing.framed_plan."""
    parts: list[ScenePart] = []
    keyed = [scene for scene in clip.scene_reframes if _keyed(scene)]
    base, frame_size = planned(work, clip) if keyed else (framed, (0, 0))
    for scene in clip.scene_reframes:
        plan = (
            keyframed_plan(base, framed, scene, frame_size) if _keyed(scene) else framed
        )
        last = parts[-1] if parts else None
        if last and last.plan is plan and last.layout == scene.layout:
            parts[-1] = ScenePart(last.start, scene.end, plan, scene.layout)
            continue
        parts.append(ScenePart(scene.start, scene.end, plan, scene.layout))
    seconds = config.settings.zoom_out.transition_s
    if seconds <= 0 or not any(_eased(parts, i) for i in range(len(parts))):
        return parts
    meta = load_meta(work)
    cuts = scene_cuts(work) if (work / SIGNALS).is_file() else []
    return add_eases(parts, (meta.width, meta.height), cuts, seconds)


def add_eases(
    parts: Sequence[ScenePart],
    frame_size: tuple[int, int],
    cuts: Sequence[float],
    seconds: float,
) -> list[ScenePart]:
    """Return parts with an ease of seconds (pipeline/zoom_transition) at
    each edge between a zoomed-out part and a fill part that no scene cut
    of cuts is at, in a frame_size source (module docstring)."""

    def box(plan: CropPlan, t: float) -> tuple[float, float, float, float]:
        center_x, center_y = window_center(plan, t, frame_size[0])
        left, top = center_x - plan.width / 2, center_y - plan.height / 2
        return left, top, plan.width, plan.height

    def at_cut(t: float) -> bool:
        return any(abs(cut - t) <= CUT_TOLERANCE_S for cut in cuts)

    eased = list(parts)
    for index, part in enumerate(parts):
        if part.layout not in ZOOM_OUT_LAYOUTS:
            continue
        before = parts[index - 1] if index > 0 else None
        after = parts[index + 1] if index + 1 < len(parts) else None
        ease_in = ease_out = None
        if before and before.layout == "fill" and not at_cut(part.start):
            ease_in = Ease(box(before.plan, part.start), frame_size, seconds)
        if after and after.layout == "fill" and not at_cut(part.end):
            ease_out = Ease(box(after.plan, part.end), frame_size, seconds)
        eased[index] = replace(part, ease_in=ease_in, ease_out=ease_out)
    return eased


def _eased(parts: Sequence[ScenePart], index: int) -> bool:
    """Return True if part index of parts is zoomed out and has a fill
    neighbour (it may get an ease)."""
    if parts[index].layout not in ZOOM_OUT_LAYOUTS:
        return False
    near = parts[max(index - 1, 0) : index + 2]
    return any(part.layout == "fill" for part in near)


def keyframed_plan(
    base: CropPlan,
    framed: CropPlan,
    scene: SceneReframe,
    frame_size: tuple[int, int],
) -> CropPlan:
    """Return the plan of a track or fixed scene: base (the planned window
    in the clip's aspect) with its fill window sized and placed by scene's
    scale and crop keyframes in a frame_size (width, height) source; a
    scene without keyframes holds framed's window at its start."""
    frame_width, frame_height = frame_size
    width = max(2, even_pixels(round(base.width * scene.scale)))
    height = max(2, even_pixels(round(base.height * scene.scale)))
    points = sorted(scene.crop_keyframes, key=lambda point: point.t)
    centers = [
        (point.t, point.x * frame_width, point.y * frame_height) for point in points
    ] or [(scene.start, *window_center(framed, scene.start, frame_width))]
    keyframes = [
        CropKeyframe(
            t=t,
            x=place_window(x, width, frame_width),
            y=place_window(y, height, frame_height),
            faces=[],
        )
        for t, x, y in centers
    ]
    return base.model_copy(
        update={
            "width": width,
            "height": height,
            "keyframes": keyframes,
            "background": framed.background,
        }
    )


def window_center(plan: CropPlan, t: float, frame_width: int) -> tuple[float, float]:
    """Return the center (x, y), in source pixels, of plan's fill window at
    t seconds of the source in a frame_width wide source; the frame's
    center line if the plan has no keyframes."""
    keyframes = plan.keyframes
    if not keyframes:
        return frame_width / 2, plan.y + plan.height / 2
    times = [keyframe.t for keyframe in keyframes]
    right = max(frame_width - plan.width, 0)
    xs = [min(max(keyframe.x, 0), right) for keyframe in keyframes]
    ys = [plan.y if keyframe.y is None else keyframe.y for keyframe in keyframes]
    return (
        interpolate(times, xs, t) + plan.width / 2,
        interpolate(times, ys, t) + plan.height / 2,
    )


def _keyed(scene: SceneReframe) -> bool:
    """Return True if scene's fill window is at its crop keyframes."""
    return scene.layout == "fill" and scene.mode != "auto"
