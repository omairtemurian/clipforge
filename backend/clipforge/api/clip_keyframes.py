"""The manual reframe endpoints (SPEC-v2 3.3): set or delete a crop
keyframe of the scene at a time of a clip (pipeline/keyframes), as the
editor's crop tool does when its box is dragged or resized at the
playhead. The keyed scenes are saved like PATCH /clips/{id} saves
scene_reframes; a clip without stored scenes is first split at its
source's scene cuts (GET /clips/{id}/scenes)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.api.deps import clip_row, get_engine, project_row, work_dir
from clipforge.api.errors import ApiError
from clipforge.clip_edit import ClipEditError, apply_patch
from clipforge.models import Clip, ClipPatch, CropKeyframeSet, CropPoint, SceneReframe
from clipforge.pipeline.keyframes import (
    KeyframeError,
    NoKeyframe,
    delete_keyframe,
    scene_index,
    set_keyframe,
)
from clipforge.pipeline.reframe import scene_cuts
from clipforge.pipeline.scenes import default_scenes
from clipforge.pipeline.step import StepError

router = APIRouter()

SceneEdit = Callable[[SceneReframe], SceneReframe]


@router.put("/clips/{clip_id}/crop-keyframes")
def set_crop_keyframe(
    clip_id: int,
    body: CropKeyframeSet,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Clip:
    """Set a crop keyframe at body.t in the scene that holds it, replacing
    any within keyframes.KEY_GAP_S, and return the clip; an auto scene
    turns fixed, and body.scale (if set) resizes the scene's window.

    404 if the clip does not exist; 422 if t is outside the clip or its
    scene is not in the fill layout; 409 while the clip renders, or if it
    has no stored scenes and its source's signals.json is missing.
    """
    point = CropPoint(t=body.t, x=body.x, y=body.y)
    return _edit_scene(
        engine, clip_id, body.t, lambda scene: set_keyframe(scene, point, body.scale)
    )


@router.delete("/clips/{clip_id}/crop-keyframes")
def delete_crop_keyframe(
    clip_id: int,
    t: Annotated[float, Query(ge=0)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> Clip:
    """Delete the crop keyframe nearest t (within keyframes.KEY_GAP_S) of
    the scene that holds t, and return the clip. 404 if the clip does not
    exist or has no keyframe there; 422 if t is outside the clip; 409 like
    PUT."""
    return _edit_scene(engine, clip_id, t, lambda scene: delete_keyframe(scene, t))


def _edit_scene(engine: Engine, clip_id: int, t: float, edit: SceneEdit) -> Clip:
    """Replace the scene of clip clip_id that holds t with edit's result,
    save the clip's scenes and return the clip (errors: see the routes)."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        clip = row.to_model()
        scenes = list(clip.scene_reframes) or _default_scenes(session, clip)
        try:
            index = scene_index(scenes, t)
            scenes[index] = edit(scenes[index])
        except KeyframeError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc
        except NoKeyframe as exc:
            raise ApiError(404, "not_found", str(exc)) from exc
        duration = project_row(session, clip.project_id).duration
        try:
            apply_patch(session, row, ClipPatch(scene_reframes=scenes), duration)
        except ClipEditError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc
        return row.to_model()


def _default_scenes(session: Session, clip: Clip) -> list[SceneReframe]:
    """Return clip split at its source's scene cuts; 409 if they are
    missing."""
    try:
        cuts = scene_cuts(work_dir(session, clip.project_id))
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    return default_scenes(clip.start, clip.end, cuts, clip.layout)
