"""Topic chapter endpoints (SPEC-v2 3.2): divide a project's transcript into
topics, and clip only the topics the user picks."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import config, usage
from clipforge.api.deps import (
    get_engine,
    get_llm,
    project_row,
    require_usage_budget,
    wake_worker,
    work_dir,
)
from clipforge.api.errors import ApiError
from clipforge.db import JobRow
from clipforge.llm import LLMClient
from clipforge.models import Chapter, Job, TopicClipRequest
from clipforge.pipeline.chapters import (
    ChapterLLMError,
    chapter_ranges,
    make_chapters,
    read_chapters,
)
from clipforge.pipeline.step import StepError
from clipforge.reprompt import RepromptRefused, enqueue_reprompt

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/projects/{project_id}/chapters")
def list_chapters(
    project_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> list[Chapter]:
    """Return the project's topic chapters in order, or none if they have
    not been made yet (POST /projects/{id}/chapters)."""
    with Session(engine) as session:
        project_row(session, project_id)
        work = work_dir(session, project_id)
    try:
        return read_chapters(work)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc


@router.post("/projects/{project_id}/chapters")
def create_chapters(
    project_id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> list[Chapter]:
    """Let the LLM divide the project's transcript into topic chapters
    (pipeline/chapters.make_chapters), replacing the earlier ones, and
    return them in order.

    Answers 409 if the project has no usable transcript, and 502 if the LLM
    cannot be reached or sends no valid chapters.
    """
    with Session(engine) as session:
        project_row(session, project_id)
        work = work_dir(session, project_id)
    try:
        with usage.recording(engine, project_id):
            return make_chapters(work, config.settings, llm)
    except ChapterLLMError as exc:
        logger.warning("project %d: no chapters: %s", project_id, exc)
        raise ApiError(502, "llm_error", str(exc)) from exc
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc


@router.post("/projects/{project_id}/clip-by-topic", status_code=202)
def clip_by_topic(
    project_id: int,
    body: TopicClipRequest,
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Job:
    """Ask the LLM for new clips of the chosen chapters only, without
    transcribing again, and return the queued reprompt job (reprompt.py).

    The clips are the project's next result set when the job is done. 409
    if the chapters have not been made, the project is not finished or a
    monthly usage cap is used up; 422 if a chapter id does not exist.
    """
    with Session(engine) as session:
        project_row(session, project_id)
        work = work_dir(session, project_id)
    try:
        chapters = read_chapters(work)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    if not chapters:
        raise ApiError(
            409, "conflict", f"project {project_id} has no chapters: make them first"
        )
    try:
        ranges = chapter_ranges(chapters, body.chapters)
    except ValueError as exc:
        raise ApiError(422, "validation_error", f"chapters: {exc}") from exc
    require_usage_budget(engine)
    try:
        job_id = enqueue_reprompt(engine, project_id, body.prompt, ranges)
    except (RepromptRefused, StepError) as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    wake_worker(request)
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        assert job is not None
        return job.to_model()
