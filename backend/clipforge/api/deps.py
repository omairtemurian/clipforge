"""Shared pieces of the API routers: the database engine, the job worker, the
LLM client, the lookups of a clip and of a project's work directory, and
the human-only guard (require_human)."""

from pathlib import Path

from fastapi import Request
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import usage
from clipforge.api.errors import ApiError, not_found
from clipforge.db import ClipRow, ProjectRow
from clipforge.job_rows import process_work_dir
from clipforge.llm import LLMClient, create_client
from clipforge.pipeline.step import StepError
from clipforge.worker_pool import WorkerPool


def get_engine(request: Request) -> Engine:
    """Return the engine that the app's lifespan opened."""
    engine: Engine = request.app.state.engine
    return engine


def wake_worker(request: Request) -> None:
    """Tell the job worker pool, if the app runs one, that a job was queued."""
    worker: WorkerPool | None = request.app.state.worker
    if worker is not None:
        worker.wake()


def get_llm(request: Request) -> LLMClient:
    """Return the app's LLM client (test mode) or the configured one."""
    llm: LLMClient | None = request.app.state.llm
    return create_client() if llm is None else llm


def clip_row(session: Session, clip_id: int) -> ClipRow:
    """Return clip clip_id's row; raises the 404 ApiError if missing."""
    row = session.get(ClipRow, clip_id)
    if row is None:
        raise not_found("clip", clip_id)
    return row


def project_row(session: Session, project_id: int) -> ProjectRow:
    """Return project project_id's row; raises the 404 ApiError if missing."""
    row = session.get(ProjectRow, project_id)
    if row is None:
        raise not_found("project", project_id)
    return row


def work_dir(session: Session, project_id: int) -> Path:
    """Return the work directory of project project_id's latest process job;
    raises the 409 ApiError if it has none."""
    try:
        return process_work_dir(session, project_id)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc


def require_usage_budget(engine: Engine) -> None:
    """Raise the 409 ApiError if a monthly usage cap is used up (a new job
    must not start; usage.check_caps)."""
    try:
        usage.check_caps(engine)
    except usage.UsageCapExceeded as exc:
        raise ApiError(409, "usage_cap_exceeded", str(exc)) from exc


# Headers that mark a call by an AI agent or script (API key, MCP server):
# a call of the owner's own app session has neither.
AGENT_HEADERS = ("x-api-key", "authorization")
PUBLIC_API_PREFIX = "/api/v1/"


def is_agent_call(request: Request) -> bool:
    """Whether the request comes from an API key or MCP client (an agent)
    rather than the owner's app session."""
    if request.url.path.startswith(PUBLIC_API_PREFIX):
        return True
    return any(header in request.headers for header in AGENT_HEADERS)


def require_human(request: Request) -> None:
    """Dependency of the human-only endpoints (publish now, queue for
    publishing, approve or reject an autopilot draft; owner's rule of
    2026-10-31, SPEC-v2 3.19): 403 human_only for a call with an API key or
    from the MCP server. Agents stop at drafts, draft schedules and review
    notes."""
    if is_agent_call(request):
        raise ApiError(
            403,
            "human_only",
            "Only the owner can approve drafts and publish or queue posts, in "
            "the ClipForge app; API keys and AI agents can make drafts, draft "
            "schedules and review notes.",
        )
