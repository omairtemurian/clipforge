"""Duplicate a clip and split a clip into two clips (SPEC-v2 3.5): the
copy and the second part are new candidate clips of the same project, not
rendered yet (clip_split)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import clip_split
from clipforge.api.deps import clip_row, get_engine, project_row
from clipforge.api.errors import ApiError
from clipforge.clip_edit import ClipEditError
from clipforge.models import Clip, ClipSplit

router = APIRouter()


@router.post("/clips/{clip_id}/duplicate", status_code=201)
def duplicate_clip(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Add a copy of the clip (its sections, edits and tracks) as a new
    candidate clip and answer it; 404 if the clip does not exist."""
    with Session(engine) as session:
        return clip_split.duplicate_clip(session, clip_row(session, clip_id)).to_model()


@router.post("/clips/{clip_id}/split", status_code=201)
def split_clip(
    clip_id: int, body: ClipSplit, engine: Annotated[Engine, Depends(get_engine)]
) -> list[Clip]:
    """Split the clip at body.at seconds of the source: it keeps what plays
    before, a new clip gets what plays after. Answers both, in order. 404 if
    the clip does not exist, 409 while it renders, 422 if the time is not in
    one of its sections or a part would not be valid."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        duration = project_row(session, row.project_id).duration
        try:
            first, second = clip_split.split_clip(session, row, body.at, duration)
        except ClipEditError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc
        return [first.to_model(), second.to_model()]
