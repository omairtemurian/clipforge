"""The version history endpoints of a clip (SPEC-v2 3.5): list its
versions, get one, undo, redo and restore.

Every edit of a clip, through any endpoint, stores a version
(clipforge.clip_versions); these endpoints read the history and move in it.
Undo, redo and restore change the clip's fields, not its rendered video:
render the clip again to apply them.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import clip_versions
from clipforge.api.deps import clip_row, get_engine
from clipforge.api.errors import ApiError
from clipforge.clip_versions import HistoryError
from clipforge.db import ClipRow
from clipforge.models import Clip, ClipHistory, ClipVersion

router = APIRouter()


@router.get("/clips/{clip_id}/versions")
def get_history(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> ClipHistory:
    """Return the clip's versions, oldest first, and the current one (404
    if the clip does not exist)."""
    with Session(engine) as session:
        clip_row(session, clip_id)
        return clip_versions.history(session, clip_id)


@router.get("/clips/{clip_id}/versions/{number}")
def get_version(
    clip_id: int, number: int, engine: Annotated[Engine, Depends(get_engine)]
) -> ClipVersion:
    """Return version number of the clip with its state (404 if the clip or
    the version does not exist)."""
    with Session(engine) as session:
        clip_row(session, clip_id)
        found = clip_versions.version(session, clip_id, number)
        if found is None:
            raise _no_version(clip_id, number)
        return found


@router.post("/clips/{clip_id}/undo")
def undo(clip_id: int, engine: Annotated[Engine, Depends(get_engine)]) -> Clip:
    """Give the clip the state of the version before the current one and
    return it. 409 if there is nothing to undo or the clip renders."""
    with Session(engine) as session:
        row = _editable_row(session, clip_id)
        try:
            clip_versions.undo(session, row)
        except HistoryError as exc:
            raise ApiError(409, "conflict", str(exc)) from exc
        return row.to_model()


@router.post("/clips/{clip_id}/redo")
def redo(clip_id: int, engine: Annotated[Engine, Depends(get_engine)]) -> Clip:
    """Give the clip the state of the version after the current one (one
    that was undone) and return it. 409 if there is nothing to redo or the
    clip renders."""
    with Session(engine) as session:
        row = _editable_row(session, clip_id)
        try:
            clip_versions.redo(session, row)
        except HistoryError as exc:
            raise ApiError(409, "conflict", str(exc)) from exc
        return row.to_model()


@router.post("/clips/{clip_id}/versions/{number}/restore")
def restore(
    clip_id: int, number: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Give the clip exactly the state of its version number, as a new
    version, and return it. 404 if the clip or the version does not exist,
    409 while the clip renders."""
    with Session(engine) as session:
        row = _editable_row(session, clip_id)
        try:
            clip_versions.restore(session, row, number)
        except LookupError as exc:
            raise _no_version(clip_id, number) from exc
        return row.to_model()


def _editable_row(session: Session, clip_id: int) -> ClipRow:
    """Return clip clip_id's row; 404 if it does not exist, 409 while it
    renders."""
    row = clip_row(session, clip_id)
    if row.status == "rendering":
        raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
    return row


def _no_version(clip_id: int, number: int) -> ApiError:
    """Return the 404 error for a missing version of a clip."""
    return ApiError(404, "not_found", f"clip {clip_id} has no version {number}")
