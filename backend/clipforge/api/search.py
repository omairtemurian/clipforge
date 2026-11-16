"""Library search endpoints (SPEC-v2 3.11), for the owner and for agents
(public API /api/v1 and MCP):

    GET  /search?q=&project_id=&limit=  -> [SearchHit] (transcripts of all
                                           projects, best first)
    POST /search/clips                  ClipFromMoment -> Clip (201)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.api.deps import get_engine, project_row, work_dir
from clipforge.api.errors import ApiError
from clipforge.clip_edit import ClipEditError
from clipforge.models import (
    SEARCH_LIMIT_MAX,
    SEARCH_QUERY_MAX,
    Clip,
    ClipFromMoment,
    SearchHit,
    Transcript,
)
from clipforge.pipeline.step import TRANSCRIPT, StepError, load_json
from clipforge.search import fts, moment
from clipforge.search.query import SearchQueryError
from clipforge.storage import StorageRefused, require_not_archived

logger = logging.getLogger(__name__)

router = APIRouter()

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("/search")
def search_library(
    engine: EngineDep,
    q: Annotated[str, Query(min_length=1, max_length=SEARCH_QUERY_MAX)],
    project_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=SEARCH_LIMIT_MAX)] = fts.DEFAULT_LIMIT,
) -> list[SearchHit]:
    """Search what is said in the transcripts of all projects (or only
    project_id's) for the words of q; "quoted words" must appear together.
    Answers the matching segments best first, each with the project, the
    second where the first match is said (start) and the text with the
    matches marked. 422 if q has no word."""
    try:
        return fts.search(engine, q, project_id=project_id, limit=limit)
    except SearchQueryError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc


@router.post("/search/clips", status_code=201)
def create_clip_from_moment(body: ClipFromMoment, engine: EngineDep) -> Clip:
    """Make a candidate clip of the project's video from the moment of a
    search hit and answer it; render it with POST /clips/{id}/render. 404 if
    the project does not exist, 409 if it has no transcript or is archived,
    422 if nothing is said at or after the moment."""
    with Session(engine) as session:
        project = project_row(session, body.project_id)
        try:
            require_not_archived(session, body.project_id)
        except StorageRefused as exc:
            raise ApiError(409, "conflict", str(exc)) from exc
        work = work_dir(session, body.project_id)
        try:
            transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
        except StepError as exc:
            raise ApiError(409, "conflict", str(exc)) from exc
        try:
            row = moment.clip_from_moment(
                session, project, transcript, body.at, body.length
            )
        except ClipEditError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc
        return row.to_model()
