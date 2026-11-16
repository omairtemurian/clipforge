"""Pro Edit editor endpoints (SPEC-v3 3.8), under /proedit: what the editor
of a variant snaps its items to, and the variant's rendered video to play
next to the original. The flag proedit.enabled turns them off like the
other Pro Edit endpoints.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import config
from clipforge.api.deps import clip_row, get_engine, work_dir
from clipforge.api.errors import ApiError
from clipforge.api.proedit import require_proedit
from clipforge.models import ProEditTiming
from clipforge.pipeline.step import StepError
from clipforge.proedit.editor_timing import editor_timing
from clipforge.proedit.plan_store import current_plan

router = APIRouter(prefix="/proedit", dependencies=[Depends(require_proedit)])

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("/clips/{clip_id}/timing")
def get_proedit_timing(clip_id: int, engine: EngineDep) -> ProEditTiming:
    """Return the frame rate, length, words and plan beats of clip clip_id
    (proedit/editor_timing). 404 if the clip does not exist; 409 if its
    project has no process job or its transcript is missing."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        work = work_dir(session, clip.project_id)
        plan = current_plan(session, clip_id)
        try:
            return editor_timing(session, work, clip, plan, config.settings.render.fps)
        except StepError as error:
            raise ApiError(409, "conflict", str(error)) from error


@router.get("/clips/{clip_id}/video")
def get_proedit_video(clip_id: int, engine: EngineDep) -> FileResponse:
    """Serve the rendered video of clip clip_id inline (the editor's Pro
    Edit preview); 404 if it does not exist or is not rendered."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
    video = Path(clip.output_path) if clip.output_path else None
    if clip.status != "rendered" or video is None or not video.is_file():
        raise ApiError(404, "not_found", f"clip {clip_id} has no rendered video")
    return FileResponse(video, media_type="video/mp4")
