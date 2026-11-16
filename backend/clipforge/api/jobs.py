"""Job endpoints (SPEC 7): a project's jobs, one job, and its progress as SSE."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from anyio import to_thread
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge.api.deps import get_engine
from clipforge.api.errors import not_found
from clipforge.db import JobRow, ProjectRow
from clipforge.models import Job

router = APIRouter()

# Seconds between two reads of the job row while a client follows its events.
POLL_INTERVAL = 0.5
# Seconds of silence after which a comment keeps the connection open.
HEARTBEAT_INTERVAL = 15.0
TERMINAL_STATUSES = ("done", "failed")


@router.get("/projects/{project_id}/jobs")
def list_project_jobs(
    project_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> list[Job]:
    """Return the jobs of a project, newest first."""
    with Session(engine) as session:
        if session.get(ProjectRow, project_id) is None:
            raise not_found("project", project_id)
        rows = session.exec(
            select(JobRow)
            .where(JobRow.project_id == project_id)
            .order_by(col(JobRow.id).desc())
        )
        return [row.to_model() for row in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, engine: Annotated[Engine, Depends(get_engine)]) -> Job:
    """Return one job."""
    return _read_job(engine, job_id)


@router.get("/jobs/{job_id}/events")
def job_events(
    job_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> StreamingResponse:
    """Stream a job's progress as server-sent events.

    Each event's data is the JSON {step, progress, status, message,
    overall_progress, eta_seconds}. One event
    is sent at once and another whenever one of the fields changes; the stream
    ends after the event with status done or failed. A job that is deleted
    while followed ends the stream too.
    """
    _read_job(engine, job_id)
    return StreamingResponse(
        _event_stream(engine, job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _read_job(engine: Engine, job_id: int) -> Job:
    """Return job job_id; raises the 404 ApiError if missing."""
    job = _find_job(engine, job_id)
    if job is None:
        raise not_found("job", job_id)
    return job


def _find_job(engine: Engine, job_id: int) -> Job | None:
    """Return job job_id, or None if it does not exist."""
    with Session(engine) as session:
        row = session.get(JobRow, job_id)
        return row.to_model() if row is not None else None


def event_payload(job: Job) -> dict[str, str | float | None]:
    """Return the fields {step, progress, status, message, overall_progress,
    eta_seconds} of a job's event.

    progress is the step's, overall_progress the whole job's; eta_seconds is
    None while unknown. message is the error of a failed job, else a sentence
    for the status.
    """
    if job.status == "failed":
        message = job.error or "The job failed."
    elif job.status == "queued":
        message = "Waiting in the queue."
    elif job.status == "running":
        message = f"Running {job.step}." if job.step else "Running."
    else:
        message = "Done."
    return {
        "step": job.step,
        "progress": job.progress,
        "status": job.status,
        "message": message,
        "overall_progress": job.overall_progress,
        "eta_seconds": job.eta_seconds,
    }


async def _event_stream(engine: Engine, job_id: int) -> AsyncIterator[str]:
    """Yield the SSE text of each change of job job_id until it ends."""
    last: dict[str, str | float | None] | None = None
    idle = 0.0
    while True:
        job = await to_thread.run_sync(_find_job, engine, job_id)
        if job is None:
            return
        payload = event_payload(job)
        if payload != last:
            last, idle = payload, 0.0
            yield f"data: {json.dumps(payload)}\n\n"
        if job.status in TERMINAL_STATUSES:
            return
        await asyncio.sleep(POLL_INTERVAL)
        idle += POLL_INTERVAL
        if idle >= HEARTBEAT_INTERVAL:
            idle = 0.0
            yield ": keep-alive\n\n"
