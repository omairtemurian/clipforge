"""Auto zoom-out moments (TASK-198): the stretches of a fill clip that are
shown zoomed out, as a square of the frame over a blurred copy
(square_blur) or the whole frame over it (fit), instead of the fill crop.

Each crop keyframe (sample, 10 a second) of an auto fill scene wants a
zoom out for a reason (spread faces, a wide shot, wide motion, a lost
subject: pipeline/zoom_out_rules), or not. Within each shot
(scenes.default_scenes at the scene cuts) the samples' wishes are averaged
over window_s; a zoom out starts where the average reaches enter and ends
where it falls to exit (hysteresis, no flapping), moved back to the
wishing samples. Runs shorter than min_segment_s join their longer
neighbour (layout_switch.smooth_runs) and zoom-outs still shorter are
dropped. Then the zoom-outs of the clip are kept, strongest (largest share
of wishing samples) and longest first, while their total stays within
max_share of the clip's length. A zoom-out is fit if at least half its
wishing samples need the whole frame (motion, or faces spread wider than
the square), else square_blur.

The thresholds are config.zoom_out's, scaled for the project's intensity
(zoom_out_rules.zoom_params).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from clipforge.models import CropKeyframe, CropPlan, Layout, SceneReframe
from clipforge.pipeline.layout_switch import smooth_runs
from clipforge.pipeline.scenes import default_scenes
from clipforge.pipeline.zoom_out_rules import (
    MotionSample,
    Reason,
    ZoomOutParams,
    sample_reasons,
)

# The layouts that a zoom-out shows.
ZOOM_OUT_LAYOUTS: tuple[Layout, ...] = ("square_blur", "fit")


@dataclass(frozen=True)
class ZoomOut:
    """A zoom-out from start to end seconds in layout; strength is the share
    of its samples that wish it."""

    start: float
    end: float
    layout: Layout
    strength: float


def shot_zoom_outs(
    shot: SceneReframe,
    samples: Sequence[CropKeyframe],
    reasons: Sequence[tuple[Reason | None, bool]],
    params: ZoomOutParams,
) -> list[ZoomOut]:
    """Return the zoom-outs of shot, whose samples have reasons
    (sample_reasons), after hysteresis and the minimum length."""
    wants = [reason is not None for reason, _ in reasons]
    times = [sample.t for sample in samples]
    zoomed = _snap(wants, _hysteresis(times, wants, params))
    runs: list[tuple[float, Layout]] = []
    for t, zoom in zip(times, zoomed, strict=True):
        layout: Layout = "fit" if zoom else "fill"
        if not runs or runs[-1][1] != layout:
            runs.append((shot.start if not runs else round(t, 3), layout))
    runs = smooth_runs(runs, shot.end, params.min_segment_s)
    zoom_outs = []
    for index, (begin, layout) in enumerate(runs):
        end = runs[index + 1][0] if index + 1 < len(runs) else shot.end
        if layout == "fill" or end - begin < params.min_segment_s:
            continue
        inside = [r for t, r in zip(times, reasons, strict=True) if begin <= t < end]
        wishing = [needs_fit for reason, needs_fit in inside if reason is not None]
        strength = len(wishing) / len(inside) if inside else 0.0
        fit = len(wishing) > 0 and sum(wishing) >= len(wishing) / 2
        zoom_outs.append(ZoomOut(begin, end, "fit" if fit else "square_blur", strength))
    return zoom_outs


def cap_share(zoom_outs: Sequence[ZoomOut], budget: float) -> list[ZoomOut]:
    """Return the zoom-outs kept, strongest and longest first (the earliest
    of a tie), while their total length stays within budget seconds; in
    time order."""
    ranked = sorted(
        zoom_outs, key=lambda z: (-round(z.strength, 6), z.start - z.end, z.start)
    )
    kept: list[ZoomOut] = []
    total = 0.0
    for zoom_out in ranked:
        length = zoom_out.end - zoom_out.start
        if total + length <= budget + 1e-6:
            kept.append(zoom_out)
            total += length
    return sorted(kept, key=lambda z: z.start)


def zoom_out_scenes(
    plan: CropPlan,
    scenes: Sequence[SceneReframe],
    frame_size: tuple[int, int],
    cuts: Sequence[float],
    motion: Sequence[MotionSample],
    params: ZoomOutParams,
) -> list[SceneReframe]:
    """Return scenes (covering the clip of plan) with the zoom-outs of their
    auto fill scenes (module docstring) cut out of them as scenes of their
    own, in a frame_size source with scene cuts at cuts and motion."""
    found: list[ZoomOut] = []
    for scene in scenes:
        if scene.layout != "fill" or scene.mode != "auto":
            continue
        for shot in default_scenes(scene.start, scene.end, cuts, "fill"):
            samples = [k for k in plan.keyframes if shot.start <= k.t < shot.end]
            reasons = sample_reasons(samples, frame_size, plan.width, motion, params)
            found += shot_zoom_outs(shot, samples, reasons, params)
    length = scenes[-1].end - scenes[0].start if scenes else 0.0
    kept = cap_share(found, params.max_share * length)
    result: list[SceneReframe] = []
    for scene in scenes:
        inside = [z for z in kept if scene.start <= z.start and z.end <= scene.end]
        result += _cut_out(scene, inside)
    return result


def _cut_out(scene: SceneReframe, zoom_outs: Sequence[ZoomOut]) -> list[SceneReframe]:
    """Return scene split into its parts outside zoom_outs (in time order,
    inside it), in its layout, and the zoom-outs in theirs."""
    parts: list[SceneReframe] = []
    begin = scene.start
    for zoom_out in zoom_outs:
        if zoom_out.start > begin:
            parts.append(
                scene.model_copy(update={"start": begin, "end": zoom_out.start})
            )
        parts.append(
            scene.model_copy(
                update={
                    "start": zoom_out.start,
                    "end": zoom_out.end,
                    "layout": zoom_out.layout,
                }
            )
        )
        begin = zoom_out.end
    if scene.end > begin:
        parts.append(scene.model_copy(update={"start": begin, "end": scene.end}))
    return parts


def _hysteresis(
    times: Sequence[float], wants: Sequence[bool], params: ZoomOutParams
) -> list[bool]:
    """Return whether each sample is zoomed out: the share of samples within
    window_s / 2 of it that want a zoom out turns it on at enter or more and
    off at exit or less, and keeps the state in between."""
    half = params.window_s / 2
    state = False
    zoomed = []
    for t in times:
        near = [w for u, w in zip(times, wants, strict=True) if abs(u - t) <= half]
        share = sum(near) / len(near)
        if not state and share >= params.enter:
            state = True
        elif state and share <= params.exit:
            state = False
        zoomed.append(state)
    return zoomed


def _snap(wants: Sequence[bool], zoomed: Sequence[bool]) -> list[bool]:
    """Return zoomed with each zoomed-out run moved back to start at the
    first of the wanting samples just before it and to end after its last
    wanting sample (the hysteresis window lags by half its width)."""
    snapped = list(zoomed)
    for index in range(1, len(snapped)):
        if snapped[index] and not snapped[index - 1]:
            back = index - 1
            while back >= 0 and wants[back] and not snapped[back]:
                snapped[back] = True
                back -= 1
    for index in range(len(snapped) - 1, -1, -1):
        last = index + 1 == len(snapped) or not snapped[index + 1]
        if snapped[index] and last and not wants[index]:
            snapped[index] = False
    return snapped
