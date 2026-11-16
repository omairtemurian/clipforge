"""PUT /projects/{id}/zoom-out: the zoom-out moments intensity of a
project (TASK-198b), saved in its settings and applied to its clips."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.api.deps import get_engine, project_row
from clipforge.api.errors import ApiError
from clipforge.job_rows import process_work_dir
from clipforge.models import ZoomOutRequest, ZoomOutResult
from clipforge.pipeline.step import StepError
from clipforge.zoom_out_apply import reapply_zoom_out

router = APIRouter()


@router.put("/projects/{project_id}/zoom-out")
def set_zoom_out(
    project_id: int,
    body: ZoomOutRequest,
    engine: Annotated[Engine, Depends(get_engine)],
) -> ZoomOutResult:
    """Save the project's zoom_out_moments and plan the zoom-outs of its
    clips that have no manual scenes again (zoom_out_apply); the rendered
    videos do not change until the clips are rendered. A project without a
    process job has no clips to plan; 409 if the job's files are not valid."""
    with Session(engine) as session:
        row = project_row(session, project_id)
        row.settings = row.settings.model_copy(
            update={"zoom_out_moments": body.intensity}
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        default = row.settings.default_layout
        try:
            work = process_work_dir(session, project_id)
        except StepError:
            return ZoomOutResult(project=row.to_model(), clip_ids=[])
    try:
        clip_ids = reapply_zoom_out(engine, work, project_id, default, body.intensity)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    with Session(engine) as session:
        project = project_row(session, project_id).to_model()
    return ZoomOutResult(project=project, clip_ids=list(clip_ids))
