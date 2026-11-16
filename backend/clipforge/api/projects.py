"""Project endpoints (SPEC 7): create from a URL or an upload, list, get,
rename, change the brand template, reprompt, process a failed one again,
delete."""

import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge.api.deps import (
    get_engine,
    project_row,
    require_usage_budget,
    wake_worker,
)
from clipforge.api.errors import ApiError
from clipforge.db import BrandTemplateRow, JobRow, ProjectRow
from clipforge.jobs import enqueue_process
from clipforge.models import (
    CREDIT_LINE_MAX,
    Job,
    ProcessingSettings,
    Project,
    ProjectCreate,
    ProjectPatch,
    RepromptRequest,
    SourceRights,
)
from clipforge.pipeline.extractors import UnsupportedSource, require_supported
from clipforge.pipeline.render import project_output
from clipforge.pipeline.step import StepError, job_dir
from clipforge.reprocess import ReprocessRefused, reprocess_project
from clipforge.reprompt import RepromptRefused, enqueue_reprompt
from clipforge.storage import StorageRefused, require_not_archived
from clipforge.uploads import uploads_dir

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/projects", status_code=201)
def create_project(
    body: ProjectCreate,
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Project:
    """Add a project for a video URL and queue its process job (409 if a
    monthly usage cap is used up, 422 unsupported_source if no yt-dlp extractor
    handles the site)."""
    require_usage_budget(engine)
    try:
        require_supported(body.url)
    except UnsupportedSource as exc:
        raise ApiError(422, "unsupported_source", str(exc)) from exc
    job_id = enqueue_process(
        engine,
        body.url,
        body.settings,
        source_rights=body.source_rights,
        credit_line=body.credit_line,
    )
    wake_worker(request)
    return project_of_job(engine, job_id)


@router.post("/projects/upload", status_code=201)
def upload_project(
    file: UploadFile,
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[str, Form()] = "{}",
    source_rights: Annotated[SourceRights | None, Form()] = None,
    credit_line: Annotated[str, Form(max_length=CREDIT_LINE_MAX)] = "",
) -> Project:
    """Add a project for an uploaded video file and queue its process job.

    settings is the JSON of a ProcessingSettings (default settings if absent);
    source_rights and credit_line are as in ProjectCreate.
    The file is saved as {data_dir}/uploads/<random id>/<its name>. 409 if a
    monthly usage cap is used up.
    """
    require_usage_budget(engine)
    try:
        processing = ProcessingSettings.model_validate_json(settings)
    except ValidationError as exc:
        problems = [
            f"settings.{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
        ]
        raise ApiError(422, "validation_error", "; ".join(problems)) from exc
    saved = _save_upload(file)
    job_id = enqueue_process(
        engine,
        str(saved),
        processing,
        source_rights=source_rights,
        credit_line=credit_line,
    )
    wake_worker(request)
    return project_of_job(engine, job_id)


@router.post("/projects/{project_id}/reprompt", status_code=202)
def reprompt_project(
    project_id: int,
    body: RepromptRequest,
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Job:
    """Ask the LLM again for the clips of a finished project with a new
    prompt, without transcribing it again, and return the queued reprompt
    job (reprompt.py).

    The new clips become the project's next result set when the job is done;
    the clips so far stay as the previous result set. 409 if the project is
    not finished (or has no transcript) or a monthly usage cap is used up.
    """
    with Session(engine) as session:
        project_row(session, project_id)
        try:
            require_not_archived(session, project_id)
        except StorageRefused as exc:
            raise ApiError(409, "conflict", str(exc)) from exc
    require_usage_budget(engine)
    try:
        job_id = enqueue_reprompt(engine, project_id, body.prompt)
    except (RepromptRefused, StepError) as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    wake_worker(request)
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        assert job is not None
        return job.to_model()


@router.post("/projects/{project_id}/reprocess", status_code=202)
def reprocess(
    project_id: int,
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Job:
    """Process a failed project again and return its queued process job: it
    resumes after the last step it finished (reprocess.py). 409 unless the
    project failed (and is not archived), or if a monthly usage cap is used
    up."""
    with Session(engine) as session:
        project_row(session, project_id)
    require_usage_budget(engine)
    try:
        job_id = reprocess_project(engine, project_id)
    except ReprocessRefused as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    wake_worker(request)
    with Session(engine) as session:
        return session.get_one(JobRow, job_id).to_model()


@router.get("/projects")
def list_projects(engine: Annotated[Engine, Depends(get_engine)]) -> list[Project]:
    """Return every project, newest first."""
    with Session(engine) as session:
        rows = session.exec(select(ProjectRow).order_by(col(ProjectRow.id).desc()))
        return [row.to_model() for row in rows]


@router.get("/projects/{project_id}")
def get_project(
    project_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Project:
    """Return one project."""
    with Session(engine) as session:
        return project_row(session, project_id).to_model()


@router.post("/projects/{project_id}/open")
def open_project(
    project_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Project:
    """Mark a project as opened (the "New" badge goes away once it is done)
    and return it; the first time it is opened counts."""
    with Session(engine) as session:
        row = project_row(session, project_id)
        if row.opened_at is None:
            row.opened_at = datetime.now(UTC)
            session.add(row)
            session.commit()
            session.refresh(row)
        return row.to_model()


@router.patch("/projects/{project_id}")
def patch_project(
    project_id: int, body: ProjectPatch, engine: Annotated[Engine, Depends(get_engine)]
) -> Project:
    """Change the brand template of the project's clips, its source rights,
    its credit line and its title (the fields sent) and return the project;
    422 if the template does not exist."""
    with Session(engine) as session:
        row = project_row(session, project_id)
        sent = body.model_fields_set
        if "brand_template_id" in sent:
            if (
                body.brand_template_id is not None
                and session.get(BrandTemplateRow, body.brand_template_id) is None
            ):
                raise ApiError(
                    422,
                    "validation_error",
                    f"brand_template_id: template {body.brand_template_id} not found",
                )
            row.settings = row.settings.model_copy(
                update={"brand_template_id": body.brand_template_id}
            )
        if "source_rights" in sent:
            row.source_rights = body.source_rights
        if "credit_line" in sent:
            row.credit_line = body.credit_line
        if "title" in sent:
            row.title = body.title.strip()
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Response:
    """Delete a project with its clips, jobs and files.

    Refused with 409 while one of its jobs is running.
    """
    with Session(engine) as session:
        row = project_row(session, project_id)
        jobs = session.exec(select(JobRow).where(JobRow.project_id == project_id)).all()
        if any(job.status == "running" for job in jobs):
            raise ApiError(
                409, "conflict", f"project {project_id} has a running job; try later"
            )
        job_ids = [job.id for job in jobs if job.id is not None]
        source_path = Path(row.source_path) if row.source_path else None
        session.delete(row)
        session.commit()
    for job_id in job_ids:
        shutil.rmtree(job_dir(job_id), ignore_errors=True)
    shutil.rmtree(project_output(project_id), ignore_errors=True)
    if source_path is not None:
        _remove_upload(source_path)
    return Response(status_code=204)


def project_of_job(engine: Engine, job_id: int) -> Project:
    """Return the project that job job_id belongs to."""
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        assert job is not None
        return project_row(session, job.project_id).to_model()


def _save_upload(file: UploadFile) -> Path:
    """Save an uploaded file in its own directory and return its path.

    Only the last component of the client's file name is used. Raises the 422
    ApiError for an empty file.
    """
    name = Path((file.filename or "").replace("\\", "/")).name or "upload"
    target = uploads_dir() / uuid.uuid4().hex / name
    target.parent.mkdir(parents=True)
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    if target.stat().st_size == 0:
        shutil.rmtree(target.parent)
        raise ApiError(422, "validation_error", f"file: {name} is empty")
    return target


def _remove_upload(path: Path) -> None:
    """Delete the directory of an uploaded video; other sources are kept."""
    if path.parent.parent == uploads_dir().absolute():
        shutil.rmtree(path.parent, ignore_errors=True)
