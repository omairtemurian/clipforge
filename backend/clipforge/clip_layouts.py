"""The layouts that a project's new clips get once they are reframed
(SPEC-v2 3.3), as the project's default layout (ProcessingSettings.
default_layout) says:

- auto: the layout that reframe chose for the clip, in its crop plan
  (reframe.choose_layout, or the genre preset's);
- dynamic: a layout per segment (pipeline/layout_switch), stored as the
  clip's scenes when they differ; the clip's layout is the one shown
  longest. A clip that has scenes already (the editor's) keeps them;
- a layout: that layout for every clip.

With auto and dynamic, the fill stretches of a clip without scenes of its
own may also zoom out for a moment (square_blur or fit), as the project's
zoom_out_moments intensity says (pipeline/layout_auto, thresholds in
config.zoom_out); the zoom-outs are stored as the clip's scenes. A layout
chosen for every clip is kept as it is.
"""

from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import config
from clipforge.clips import get_clip_row
from clipforge.db import ClipRow
from clipforge.models import (
    CropPlan,
    DefaultLayout,
    SceneReframe,
    ZoomOutIntensity,
)
from clipforge.pipeline.layout_auto import zoom_out_scenes
from clipforge.pipeline.layout_switch import main_layout, switch_scenes
from clipforge.pipeline.motion_spread import motion_spread
from clipforge.pipeline.reframe import crop_path, scene_cuts
from clipforge.pipeline.step import SIGNALS, SOURCE, load_json, load_meta
from clipforge.pipeline.zoom_out_rules import MotionSample, ZoomOutParams, zoom_params


def load_plan(work: Path, clip_id: int) -> CropPlan:
    """Return the crop plan of clip clip_id in the job work directory work;
    raises StepError if it is missing or not valid."""
    return load_json(crop_path(work, clip_id), CropPlan, "reframe")


def set_planned_layouts(
    engine: Engine,
    work: Path,
    clip_ids: Sequence[int],
    default: DefaultLayout = "auto",
    zoom_out: ZoomOutIntensity = "off",
) -> None:
    """Set the layout of each of the clips clip_ids, whose crop plans are in
    the job work directory work, as default and zoom_out say (module
    docstring).

    Raises StepError if a clip or its crop plan does not exist, if work's
    meta.json is missing or not valid for dynamic or a zoom-out, and if its
    signals.json is for dynamic (a zoom-out without it sees no scene cuts).
    """
    dynamic = default == "dynamic"
    params = zoom_params(zoom_out, config.settings.zoom_out)
    if default not in ("auto", "dynamic"):
        params = None
    scenic = dynamic or params is not None
    has_cuts = dynamic or (scenic and (work / SIGNALS).is_file())
    cuts = scene_cuts(work) if has_cuts else []
    meta = load_meta(work) if scenic else None
    frame_size = (meta.width, meta.height) if meta else (0, 0)
    with Session(engine) as session:
        for clip_id in clip_ids:
            clip = get_clip_row(session, clip_id)
            plan = load_plan(work, clip_id)
            if default == "auto" and clip.scene_reframes:
                clip.layout = plan.layout
            elif default == "auto" or default == "dynamic":
                if not clip.scene_reframes:
                    _plan_scenes(clip, work, plan, (frame_size, cuts), dynamic, params)
            else:
                clip.layout = default
            session.add(clip)
        session.commit()


def _plan_scenes(
    clip: ClipRow,
    work: Path,
    plan: CropPlan,
    source: tuple[tuple[int, int], Sequence[float]],
    dynamic: bool,
    params: ZoomOutParams | None,
) -> None:
    """Set the layout and scenes of clip, which has none, from plan: a
    layout per segment (layout_switch) if dynamic, else plan's layout
    throughout; with the zoom-outs of params, if set (_zoom_out), in a
    source of (frame size, scene cuts). Scenes are stored only if they
    differ from the clip's layout, the one shown longest."""
    frame_size, cuts = source
    model = clip.to_model()
    if dynamic:
        scenes = switch_scenes(plan, model.start, model.end, frame_size[0], cuts)
    else:
        scenes = [SceneReframe(start=model.start, end=model.end, layout=plan.layout)]
    if params is not None:
        scenes = _zoom_out(work, plan, scenes, frame_size, cuts, params)
    clip.layout = main_layout(scenes)
    if any(scene.layout != clip.layout for scene in scenes):
        clip.scene_reframes = scenes


def _zoom_out(
    work: Path,
    plan: CropPlan,
    scenes: list[SceneReframe],
    frame_size: tuple[int, int],
    cuts: Sequence[float],
    params: ZoomOutParams,
) -> list[SceneReframe]:
    """Return scenes with the zoom-outs of plan's clip (layout_auto) in a
    frame_size source with scene cuts at cuts; its motion spread is measured
    from work's source.mp4 only if a sample shows nobody."""
    source = work / SOURCE
    nobody = any(
        all(face.kind == "object" for face in keyframe.faces)
        for keyframe in plan.keyframes
    )
    motion: list[MotionSample] = []
    if nobody and source.is_file() and _has_fill(scenes):
        motion = motion_spread(source, plan.start, plan.end, cuts)
    return zoom_out_scenes(plan, scenes, frame_size, cuts, motion, params)


def _has_fill(scenes: Sequence[SceneReframe]) -> bool:
    """Return True if one of scenes is in the fill layout."""
    return any(scene.layout == "fill" for scene in scenes)
