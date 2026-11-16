"""Resumable chunked upload endpoints (SPEC-v2 3.1): open a session, send
the file in chunks, ask how far it got, then turn it into a project.

    POST   /uploads                 {filename, size}       -> UploadSession
    GET    /uploads/{id}                                   -> UploadSession
    PATCH  /uploads/{id}?offset=N   chunk bytes,
                                    X-Chunk-SHA256 header  -> UploadSession
    POST   /uploads/{id}/complete   UploadComplete         -> Project
    DELETE /uploads/{id}                                   -> 204

The bytes live in clipforge.uploads until complete moves them where
POST /projects/upload would have saved them.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from starlette.concurrency import run_in_threadpool

from clipforge import uploads
from clipforge.api.deps import get_engine, require_usage_budget, wake_worker
from clipforge.api.errors import ApiError
from clipforge.api.projects import project_of_job
from clipforge.jobs import enqueue_process
from clipforge.models import (
    CREDIT_LINE_MAX,
    ProcessingSettings,
    Project,
    SourceRights,
)

router = APIRouter()

CHECKSUM_HEADER = "X-Chunk-SHA256"


class UploadCreate(BaseModel):
    """The body of POST /uploads: the file's name and its size in bytes (at
    most 30 GB)."""

    filename: str = Field(min_length=1, max_length=255)
    size: int


class UploadSession(BaseModel):
    """An upload: its id, file name, size and the bytes received so far (the
    offset of the next chunk)."""

    id: str
    filename: str
    size: int
    offset: int


class UploadComplete(BaseModel):
    """The body of POST /uploads/{id}/complete: how to process the video and
    its source rights, as in ProjectCreate."""

    settings: ProcessingSettings = Field(default_factory=ProcessingSettings)
    source_rights: SourceRights | None = None
    credit_line: str = Field(default="", max_length=CREDIT_LINE_MAX)


@router.post("/uploads", status_code=201)
def create_upload(body: UploadCreate) -> UploadSession:
    """Open an upload session; 422 for an empty or over-30-GB size, 507
    insufficient_storage if the disk has too little free space."""
    return _session(lambda: uploads.create(body.filename, body.size))


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: str) -> UploadSession:
    """Return the session, whose offset is where the client resumes."""
    return _session(lambda: uploads.status(upload_id))


@router.patch("/uploads/{upload_id}")
async def append_chunk(
    upload_id: str,
    request: Request,
    offset: Annotated[int, Query(ge=0)],
    sha256: Annotated[str, Header(alias=CHECKSUM_HEADER)],
) -> UploadSession:
    """Append the request body at offset; 409 offset_mismatch if offset is not
    the bytes received so far, 422 checksum_mismatch if the body's SHA-256 is
    not the header's, 413 for a chunk over 64 MB."""
    chunk = await _read_chunk(request)
    return await run_in_threadpool(
        _session, lambda: uploads.append(upload_id, offset, chunk, sha256)
    )


@router.post("/uploads/{upload_id}/complete", status_code=201)
def complete_upload(
    upload_id: str,
    body: UploadComplete,
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Project:
    """Add a project for the uploaded video and queue its process job; 409
    upload_incomplete if bytes are missing, 409 if a monthly usage cap is
    used up (the upload is then kept)."""
    require_usage_budget(engine)
    try:
        path = uploads.finish(upload_id)
    except uploads.UploadError as exc:
        raise ApiError(exc.status, exc.code, exc.message) from exc
    job_id = enqueue_process(
        engine,
        str(path),
        body.settings,
        source_rights=body.source_rights,
        credit_line=body.credit_line,
    )
    wake_worker(request)
    return project_of_job(engine, job_id)


@router.delete("/uploads/{upload_id}", status_code=204)
def cancel_upload(upload_id: str) -> Response:
    """Drop the session and the bytes received."""
    try:
        uploads.cancel(upload_id)
    except uploads.UploadError as exc:
        raise ApiError(exc.status, exc.code, exc.message) from exc
    return Response(status_code=204)


def _session(action: Callable[[], uploads.UploadState]) -> UploadSession:
    """Run action and return its state as an UploadSession, turning an
    UploadError into the ApiError."""
    try:
        state = action()
    except uploads.UploadError as exc:
        raise ApiError(exc.status, exc.code, exc.message) from exc
    return UploadSession(
        id=state.id, filename=state.filename, size=state.size, offset=state.offset
    )


async def _read_chunk(request: Request) -> bytes:
    """Return the request body; 413 chunk_too_large past MAX_CHUNK_BYTES."""
    parts: list[bytes] = []
    received = 0
    async for part in request.stream():
        received += len(part)
        if received > uploads.MAX_CHUNK_BYTES:
            raise ApiError(
                413,
                "chunk_too_large",
                f"a chunk may have at most {uploads.MAX_CHUNK_BYTES} bytes",
            )
        parts.append(part)
    return b"".join(parts)
