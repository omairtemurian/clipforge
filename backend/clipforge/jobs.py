"""The jobs of the job table: queueing, claiming and running them.

A job is queued when it is added (enqueue_process for a new project's process
job, enqueue_render for one clip's render job), with an integer priority.
claim_next atomically marks the next queued job running (highest priority,
then oldest) and counts the attempt (Job.attempts); run_claimed runs it in
its own work directory: a process job with process.run_process_job, a
reprompt job with reprompt.run_reprompt_job, a render job with
clips.render_clip_row. Job.step, Job.progress, Job.status
and Job.error follow the work, and the log records of the run go to the
job's log_path. The worker threads that claim and run the jobs are in
clipforge.worker_pool.

A job is running only while a worker is working on it, so the jobs that a
stopped or killed process left running go back to queued
(reset_stale_jobs, called by WorkerPool.start) and a process job resumes
after the last step it finished (SPEC-v2 2.2). A job that was running at
job_max_attempts such stops is a poison job (it may be what stops the
process): it fails instead of running again.
"""

import logging
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select, update

from clipforge import config, job_progress, notifications, usage
from clipforge.clip_crop import ensure_crop_plan
from clipforge.clips import render_clip_row
from clipforge.db import ClipRow, JobRow, ProjectRow
from clipforge.job_rows import process_work_dir, record_progress
from clipforge.joblog import job_log
from clipforge.llm import LLMClient
from clipforge.models import JobKind, ProcessingSettings, SourceRights
from clipforge.pipeline.step import StepError, job_dir
from clipforge.process import JOB_LOG, create_job, run_process_job
from clipforge.process_clips import RENDER_STEP
from clipforge.proedit.run_job import run_proedit_job
from clipforge.proedit.runs import fail_job_runs
from clipforge.reprompt import restore_project, run_reprompt_job

logger = logging.getLogger(__name__)

# The priority of the projects of a watched creator's new upload (T28c):
# they go before every job queued with the default priority 0.
TOP_PRIORITY = 100
# The priority of the new upload of a campaign creator (T58b.1): before the
# other watched creators' uploads.
CAMPAIGN_PRIORITY = 200
# The kinds of job that keep their project's status (queued, running) while
# they are queued or run: its process job and its reprompts.
PROJECT_JOB_KINDS = ("process", "reprompt")


@dataclass(frozen=True)
class ClaimedJob:
    """A job that claim_next marked running: what a worker needs to run it."""

    id: int
    kind: JobKind
    project_id: int
    clip_id: int | None


def enqueue_process(
    engine: Engine,
    source: str,
    processing: ProcessingSettings,
    *,
    source_rights: SourceRights | None = None,
    credit_line: str = "",
    priority: int = 0,
    campaign_id: int | None = None,
    source_published_at: datetime | None = None,
) -> int:
    """Add a project for source (a URL or a file) and a queued process job
    with priority for it; return the job id (process.create_job)."""
    return create_job(
        engine,
        source,
        processing,
        source_rights=source_rights,
        credit_line=credit_line,
        priority=priority,
        campaign_id=campaign_id,
        source_published_at=source_published_at,
    )


def enqueue_render(engine: Engine, clip_id: int, *, priority: int = 0) -> int:
    """Add a queued render job with priority for clip clip_id; return its id.

    The job renders the clip from the work directory of its project's latest
    process job. Raises StepError if the clip or a process job of its
    project does not exist.
    """
    with Session(engine) as session:
        clip = session.get(ClipRow, clip_id)
        if clip is None:
            raise StepError(f"clip {clip_id} not found")
        process_work_dir(session, clip.project_id)
        job = JobRow(
            project_id=clip.project_id,
            clip_id=clip_id,
            kind="render",
            step="",
            log_path="",
            priority=priority,
        )
        session.add(job)
        session.flush()
        assert job.id is not None
        job.log_path = str(job_dir(job.id) / JOB_LOG)
        session.commit()
        return job.id


def reset_stale_jobs(engine: Engine, max_attempts: int | None = None) -> list[int]:
    """Queue the running jobs again and return their ids.

    Run before the worker starts, when no job can really be running: they
    are left by a process that stopped in the middle of them. Their step,
    progress and error are cleared and a process job's project is queued;
    the files of the steps they finished stay, so they resume. A job that
    already had max_attempts attempts (default: the job_max_attempts
    setting) fails instead, with its project if it is a process job and
    its clips that were rendering (fail_poison_job).
    """
    limit = config.settings.job_max_attempts if max_attempts is None else max_attempts
    with Session(engine) as session:
        stale = session.exec(select(JobRow).where(JobRow.status == "running")).all()
        queued: list[int | None] = []
        poison: list[int | None] = []
        for job in stale:
            if job.attempts >= limit:
                _fail_poison_job(session, job)
                poison.append(job.id)
                continue
            job.status, job.step, job.progress, job.error = "queued", "", 0.0, None
            job.overall_progress, job.eta_seconds = 0.0, None
            if job.kind in PROJECT_JOB_KINDS:
                project = _get_project(session, job.project_id)
                project.status = "queued"
                project.overall_progress, project.eta_seconds = 0.0, None
            queued.append(job.id)
        session.commit()
    if queued:
        logger.warning("jobs %s were running when the worker stopped: queued", queued)
    if poison:
        logger.error("jobs %s stopped the worker %d times: failed", poison, limit)
    return [job_id for job_id in queued if job_id is not None]


def _fail_poison_job(session: Session, job: JobRow) -> None:
    """Fail job, which was running at each of its attempts when the worker
    stopped, with its project if it is a process job; its clips that were
    rendering (the job's clip for a render or Pro Edit job) fail too, and
    so do a Pro Edit job's unfinished runs."""
    job.status = "failed"
    job.error = (
        f"the app stopped while this job was running, {job.attempts} times;"
        " it is not run again (see the job log)"
    )
    if job.kind == "process":
        _get_project(session, job.project_id).status = "failed"
    if job.kind == "reprompt":
        restore_project(session, job.project_id)
    rendering = select(ClipRow).where(
        ClipRow.project_id == job.project_id, ClipRow.status == "rendering"
    )
    if job.kind in ("render", "proedit"):
        rendering = rendering.where(ClipRow.id == job.clip_id)
    if job.kind == "proedit":
        assert job.id is not None
        fail_job_runs(session, job.id, job.error)
    for clip in session.exec(rendering).all():
        clip.status, clip.output_path = "failed", None


def claim_next(
    engine: Engine, kinds: Collection[str] | None = None
) -> ClaimedJob | None:
    """Mark the next queued job running and return it; None if none is queued.

    The next job has the highest priority, then the lowest id, among the
    queued jobs whose kind is in kinds (default: any kind). One UPDATE ...
    RETURNING statement picks and marks it and counts the attempt
    (Job.attempts), so two workers, even in two processes, never claim the
    same job. A process job's project is marked running in the same
    transaction.
    """
    queued = select(JobRow.id).where(col(JobRow.status) == "queued")
    if kinds is not None:
        if not kinds:
            return None
        queued = queued.where(col(JobRow.kind).in_(sorted(kinds)))
    next_id = (
        queued.order_by(col(JobRow.priority).desc(), col(JobRow.id))
        .limit(1)
        .scalar_subquery()
    )
    claim = (
        update(JobRow)
        .where(col(JobRow.id) == next_id)
        .values(status="running", error=None, attempts=col(JobRow.attempts) + 1)
        .returning(
            col(JobRow.id),
            col(JobRow.kind),
            col(JobRow.project_id),
            col(JobRow.clip_id),
        )
    )
    with engine.begin() as conn:
        row = conn.execute(claim).first()
        if row is None or row[0] is None:
            return None
        job = ClaimedJob(id=row[0], kind=row[1], project_id=row[2], clip_id=row[3])
        if job.kind in PROJECT_JOB_KINDS:
            conn.execute(
                update(ProjectRow)
                .where(col(ProjectRow.id) == job.project_id)
                .values(status="running", overall_progress=0.0, eta_seconds=None)
            )
    return job


def run_claimed(
    engine: Engine,
    job: ClaimedJob,
    *,
    llm: LLMClient | None = None,
    transcript: Path | None = None,
) -> None:
    """Run job, which claim_next marked running, to its end.

    The job is done, or failed with the error that stopped it: a job's
    failure is logged and never raised. llm and transcript are for process
    jobs (process.run_process_job); llm also plans and judges Pro Edit jobs
    (proedit/run_job.py). The seconds the job took and the tokens
    its LLM calls used go to the usage meter (usage.job_usage).
    """
    with usage.job_usage(engine, job.project_id):
        try:
            if job.kind == "process":
                run_process_job(engine, job.id, llm=llm, transcript=transcript)
            elif job.kind == "reprompt":
                run_reprompt_job(engine, job.id, llm=llm)
            elif job.kind == "proedit":
                run_proedit_job(engine, job.id, llm=llm)
            else:
                assert job.clip_id is not None
                _run_render(engine, job.id, job.project_id, job.clip_id)
        except Exception as exc:
            logger.exception("job %d failed", job.id)
            _fail(engine, job.id, str(exc))
        finally:
            job_progress.etas.forget(job.id)
    notifications.quota_warnings(engine)


def run_next(
    engine: Engine,
    *,
    llm: LLMClient | None = None,
    transcript: Path | None = None,
) -> bool:
    """Claim the next queued job (claim_next) and run it to its end
    (run_claimed); return False if no job is queued."""
    job = claim_next(engine)
    if job is None:
        return False
    run_claimed(engine, job, llm=llm, transcript=transcript)
    return True


def _run_render(engine: Engine, job_id: int, project_id: int, clip_id: int) -> None:
    """Run render job job_id, which renders clip clip_id of project project_id.

    A clip made after its project was processed (a library search moment)
    is reframed first (clip_crop.ensure_crop_plan). The job is done if the
    clip is rendered. Raises StepError if the clip is not rendered, and
    whatever ensure_crop_plan and render_clip_row raise.
    """
    with Session(engine) as session:
        work = process_work_dir(session, project_id)
        job = session.get(JobRow, job_id)
        assert job is not None
        record_progress(session, job, RENDER_STEP, 0.0)
        session.commit()
        log_path = Path(job.log_path)
    with job_log(log_path):
        ensure_crop_plan(engine, clip_id, work)
        clip = render_clip_row(engine, clip_id, work)
    if clip.status != "rendered":
        raise StepError(f"clip {clip_id} failed to render (see {log_path})")
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        assert job is not None
        record_progress(session, job, RENDER_STEP, 1.0)
        job.status = "done"
        session.commit()


def _fail(engine: Engine, job_id: int, error: str) -> None:
    """Set job job_id failed with error unless it already is; a process
    job's project fails with it."""
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        if job is None or job.status == "failed":
            return
        job.status, job.error = "failed", error
        if job.kind == "process":
            _get_project(session, job.project_id).status = "failed"
        elif job.kind == "reprompt":
            restore_project(session, job.project_id)
        session.commit()


def _get_project(session: Session, project_id: int) -> ProjectRow:
    """Return project project_id's row; raises StepError if it is missing."""
    project = session.get(ProjectRow, project_id)
    if project is None:
        raise StepError(f"project {project_id} not found")
    return project
