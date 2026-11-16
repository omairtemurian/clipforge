"""Reprocess (SPEC-v2 3.11): process a failed project again.

The project's latest process job is queued again with its attempts, step,
progress and error cleared, and the project is queued with it. The files of
the steps the job finished stay in its work directory, so it resumes after
the last of them (pipeline/step.step_done), like a job that a stopped app
left running (jobs.reset_stale_jobs).
"""

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge.db import JobRow, ProjectRow
from clipforge.pipeline.step import StepError


class ReprocessRefused(Exception):
    """The project cannot be processed again now; the message says why."""


def reprocess_project(engine: Engine, project_id: int) -> int:
    """Queue project project_id's latest process job again and return its id.

    Raises StepError if the project does not exist and ReprocessRefused
    unless it failed, is not archived and has a process job.
    """
    with Session(engine) as session:
        project = session.get(ProjectRow, project_id)
        if project is None:
            raise StepError(f"project {project_id} not found")
        if project.archived_at is not None:
            raise ReprocessRefused(f"project {project_id} is archived")
        if project.status != "failed":
            raise ReprocessRefused(
                f"project {project_id} is {project.status}; only a failed"
                " project can be processed again"
            )
        job = session.exec(
            select(JobRow)
            .where(JobRow.project_id == project_id, JobRow.kind == "process")
            .order_by(col(JobRow.id).desc())
        ).first()
        if job is None or job.id is None:
            raise ReprocessRefused(f"project {project_id} has no process job")
        job.status, job.step, job.progress, job.error = "queued", "", 0.0, None
        job.attempts, job.overall_progress, job.eta_seconds = 0, 0.0, None
        project.status = "queued"
        project.overall_progress, project.eta_seconds = 0.0, None
        session.add_all([job, project])
        session.commit()
        return job.id
