"""PUT /projects/{id}/camera-motion: the camera motion of a project's crop
windows (steering: calmer auto-track), saved in its settings and applied
to its clips' crop plans."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.api.deps import get_engine, project_row
from clipforge.api.errors import ApiError
from clipforge.camera_motion_apply import retrack_project
from clipforge.job_rows import process_work_dir
from clipforge.models import CameraMotionRequest, CameraMotionResult
from clipforge.pipeline.step import StepError

router = APIRouter()


@router.put("/projects/{project_id}/camera-motion")
def set_camera_motion(
    project_id: int,
    body: CameraMotionRequest,
    engine: Annotated[Engine, Depends(get_engine)],
) -> CameraMotionResult:
    """Save the project's camera_motion and plan the windows of its clips'
    crop plans again with it (camera_motion_apply); the rendered videos do
    not change until the clips are rendered. A project without a process
    job has no plans; 409 if the job's files are not valid."""
    with Session(engine) as session:
        row = project_row(session, project_id)
        row.settings = row.settings.model_copy(
            update={"camera_motion": body.camera_motion}
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        try:
            work = process_work_dir(session, project_id)
        except StepError:
            return CameraMotionResult(project=row.to_model(), clip_ids=[])
    try:
        clip_ids = retrack_project(engine, work, project_id, body.camera_motion)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    with Session(engine) as session:
        project = project_row(session, project_id).to_model()
    return CameraMotionResult(project=project, clip_ids=list(clip_ids))
