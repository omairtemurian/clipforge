"""Reading and updating the job row of a running job: its project, its
step and its progress (shared by clipforge.process and process_clips)."""

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge import job_progress
from clipforge.db import JobRow, ProjectRow
from clipforge.pipeline.step import StepError, job_dir


def load_job(session: Session, job_id: int) -> tuple[JobRow, ProjectRow]:
    """Return the rows of job job_id and its project.

    Raises StepError if either one does not exist.
    """
    job = session.get(JobRow, job_id)
    if job is None:
        raise StepError(f"job {job_id} not found")
    project = session.get(ProjectRow, job.project_id)
    if project is None:
        raise StepError(f"project {job.project_id} of job {job_id} not found")
    return job, project


def record_progress(session: Session, job: JobRow, step: str, progress: float) -> None:
    """Set the step and the progress (0 to 1) of job in step of the job, and
    with them its overall progress and ETA (job_progress); a process or
    reprompt job's project gets the same overall progress and ETA. The caller
    commits."""
    job.step, job.progress = step, progress
    overall = round(job_progress.overall_progress(job.kind, step, progress), 4)
    assert job.id is not None
    eta = job_progress.etas.update(job.id, step, overall)
    job.overall_progress = overall
    job.eta_seconds = None if eta is None or overall >= 1.0 else round(eta, 1)
    session.add(job)
    if job.kind in ("process", "reprompt"):
        project = session.get(ProjectRow, job.project_id)
        if project is not None:
            project.overall_progress = overall
            project.eta_seconds = job.eta_seconds
            session.add(project)


def set_step(engine: Engine, job_id: int, step: str) -> None:
    """Set Job.step of job job_id to step, at progress 0."""
    with Session(engine) as session:
        job, _ = load_job(session, job_id)
        record_progress(session, job, step, 0.0)
        session.commit()


def save_progress(engine: Engine, job_id: int, progress: float) -> None:
    """Set Job.progress of job job_id (and its overall progress and ETA)."""
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        if job is not None:
            record_progress(session, job, job.step, progress)
            session.commit()


def progress_writer(engine: Engine, job_id: int) -> Callable[[float], None]:
    """Return an on_progress callback that saves the job's progress.

    Progress is rounded to 0.01 and only written when that value changes.
    """
    saved: float | None = None

    def write(fraction: float) -> None:
        nonlocal saved
        progress = round(fraction, 2)
        if progress != saved:
            saved = progress
            save_progress(engine, job_id, progress)

    return write


def process_work_dir(session: Session, project_id: int) -> Path:
    """Return the work directory of the latest process job of a project.

    Raises StepError if the project has no process job.
    """
    job_id = session.exec(
        select(JobRow.id)
        .where(JobRow.project_id == project_id, JobRow.kind == "process")
        .order_by(col(JobRow.id).desc())
    ).first()
    if job_id is None:
        raise StepError(f"project {project_id} has no process job")
    return job_dir(job_id)
