"""Storage manager endpoints (SPEC-v2 3.11): disk use per project, clean up
and archive (clipforge/storage.py).

    GET  /storage                  -> StorageReport
    POST /projects/{id}/cleanup    -> StorageCleanup
    POST /projects/{id}/archive    -> StorageCleanup
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from clipforge import storage
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError, not_found
from clipforge.models import StorageCleanup, StorageReport
from clipforge.pipeline.step import StepError

router = APIRouter()

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("/storage")
def get_storage(engine: EngineDep) -> StorageReport:
    """Return the disk space each project uses (uploaded source, work files,
    output), largest first, their sum and the free space on the disk."""
    return storage.storage_report(engine)


@router.post("/projects/{project_id}/cleanup")
def cleanup_project_files(project_id: int, engine: EngineDep) -> StorageCleanup:
    """Delete the project's files it can do without (extracted audio, face
    cache, cached previews and, once it is done, the uploaded copy of its
    video); its clips can still be edited and rendered. 409 while it is
    queued or running."""
    try:
        return storage.cleanup_project(engine, project_id)
    except StepError as exc:
        raise not_found("Project", project_id) from exc
    except storage.StorageRefused as exc:
        raise ApiError(409, "conflict", str(exc)) from exc


@router.post("/projects/{project_id}/archive")
def archive_project_files(project_id: int, engine: EngineDep) -> StorageCleanup:
    """Archive the project: keep its rendered clips, exports, transcript and
    thumbnail, delete its source video and work files. Its clips can no
    longer be rendered. 409 while it is queued or running."""
    try:
        return storage.archive_project(engine, project_id)
    except StepError as exc:
        raise not_found("Project", project_id) from exc
    except storage.StorageRefused as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
