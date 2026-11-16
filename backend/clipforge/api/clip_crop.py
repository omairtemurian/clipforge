"""The crop endpoints of the editor's crop tool and scenes (SPEC 7): the
fill window that reframe planned for a clip, in any aspect, the clip's
scenes, the keyframes that follow a subject clicked in a scene, and the
genre reframing presets."""

from contextlib import ExitStack
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import config
from clipforge.api.deps import clip_row, get_engine, work_dir
from clipforge.api.errors import ApiError
from clipforge.ffmpeg import FFmpegError
from clipforge.models import (
    Aspect,
    ClipScenes,
    CropTrack,
    ReframePresetInfo,
    SceneTrack,
    SceneTrackRequest,
)
from clipforge.pipeline.click_track import opencv_tracker, track_scene
from clipforge.pipeline.detectors import DetectFaces, face_detector
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.framing import crop_track
from clipforge.pipeline.reframe import scene_cuts
from clipforge.pipeline.reframe_presets import preset_infos
from clipforge.pipeline.scenes import EDGE_TOLERANCE_S, default_scenes
from clipforge.pipeline.step import SOURCE, StepError, load_meta

router = APIRouter()


@router.get("/reframe-presets")
def list_reframe_presets() -> list[ReframePresetInfo]:
    """Return the genre reframing presets and the layout and tracking
    parameters each sets (pipeline/reframe_presets)."""
    return preset_infos()


@router.get("/clips/{clip_id}/crop")
def get_clip_crop(
    clip_id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    aspect: Aspect | None = None,
) -> CropTrack:
    """Return the fill window that reframe planned for the clip in aspect
    (the clip plan's if unset), which the crop tool moves and sizes
    (framing.crop_track). 404 if the clip does not exist; 409 if its crop
    plan, or the source's meta.json or signals.json, is missing."""
    with Session(engine) as session:
        work = work_dir(session, clip_row(session, clip_id).project_id)
    try:
        return crop_track(work, clip_id, aspect)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc


@router.get("/clips/{clip_id}/scenes")
def get_clip_scenes(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> ClipScenes:
    """Return the scene cuts of the clip's source and the clip's scenes:
    as stored, else split at the cuts inside it (scenes.default_scenes).
    404 if the clip does not exist; 409 if the source's signals.json is
    missing."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        work = work_dir(session, clip.project_id)
    try:
        cuts = scene_cuts(work)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    scenes = clip.scene_reframes or default_scenes(
        clip.start, clip.end, cuts, clip.layout
    )
    return ClipScenes(cuts=sorted(cuts), scenes=scenes)


@router.post("/clips/{clip_id}/scenes/track")
def track_clip_scene(
    clip_id: int,
    request: SceneTrackRequest,
    engine: Annotated[Engine, Depends(get_engine)],
) -> SceneTrack:
    """Return the crop keyframes that follow the subject of request's seed
    through the scene request.start to request.end of the clip
    (click_track.track_scene). 404 if the clip does not exist; 422 if the
    scene is not inside the clip; 409 if the source or its meta.json is
    missing or cannot be decoded."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        work = work_dir(session, clip.project_id)
    inside = clip.start - EDGE_TOLERANCE_S <= request.start
    if not inside or request.end > clip.end + EDGE_TOLERANCE_S:
        raise ApiError(422, "validation_error", "the scene must be inside the clip")
    try:
        meta = load_meta(work)
        with ExitStack() as stack:
            detect = _detector(stack, needed=not request.seed.width)
            keyframes, seed = track_scene(
                work / SOURCE,
                (meta.width, meta.height),
                sample_times(request.start, request.end),
                request.seed,
                detect,
            )
    except (StepError, FFmpegError) as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    return SceneTrack(keyframes=keyframes, seed=seed)


def _detector(stack: ExitStack, needed: bool) -> DetectFaces | None:
    """Return the face detector, entered on stack, if a click needs it to
    pick its subject or OpenCV has no tracker; None if not needed or its
    models are not downloaded (a click then tracks a box around it)."""
    if not needed and opencv_tracker() is not None:
        return None
    try:
        return stack.enter_context(face_detector(config.settings))
    except StepError:
        return None
