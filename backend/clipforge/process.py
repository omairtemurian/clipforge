"""The process job: from a project's source video to its rendered clips.

`clipforge run` adds a project and its process job (create_job) and runs the
job (run_process_job): the steps of STEP_NAMES in {data_dir}/work/{job_id},
then the clips that score kept and snap cut between words (snapped.json)
become the project's clips, which are reframed and rendered to
{data_dir}/output/{project_id}/{clip_id}.mp4 (clipforge.process_clips).
The job row follows the work: its step, its progress through that step from
0 to 1, and its status, which is running and then done, or failed with the
error. The log records of the run also go to the job's log_path, job.log in
its work directory. Each finished step leaves a marker in the work
directory, so a job that runs again resumes after its last finished step
(SPEC-v2 2.2).
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import job_progress, notifications, webhook_events
from clipforge.autopilot import safety
from clipforge.autopilot.pipeline import drafts_after_job
from clipforge.db import JobRow, ProjectRow
from clipforge.job_rows import (
    load_job,
    progress_writer,
    record_progress,
    save_progress,
)
from clipforge.joblog import job_log
from clipforge.llm import LLMClient
from clipforge.models import Clip, JobStatus, ProcessingSettings, SourceRights
from clipforge.pipeline.download import is_url
from clipforge.pipeline.step import (
    STEP_NAMES,
    THUMB,
    TRANSCRIPT,
    StepSettings,
    done_steps,
    job_dir,
    load_meta,
    load_step,
    mark_done,
    step_done,
)
from clipforge.process_clips import clear_unsaved_clips, make_clips
from clipforge.search.fts import index_quietly

logger = logging.getLogger(__name__)

JOB_LOG = "job.log"


def create_job(
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
    """Add a project for source and a queued process job for it; return the job id.

    source is an http(s) URL or a local file, which is stored as an absolute
    path. The project's title, duration and thumbnail are filled in when its
    job has ingested the source. source_rights and credit_line are stored as
    given (rights are unset by default); the job gets priority. campaign_id
    and source_published_at are stored as given (the caller has applied the
    campaign's settings).
    """
    url = is_url(source)
    with Session(engine) as session:
        project = ProjectRow(
            source_url=source if url else None,
            source_path="" if url else str(Path(source).absolute()),
            title="",
            duration=0.0,
            thumbnail_path="",
            settings=processing,
            source_rights=source_rights,
            credit_line=credit_line,
            campaign_id=campaign_id,
            source_published_at=source_published_at,
        )
        session.add(project)
        session.flush()
        assert project.id is not None
        job = JobRow(project_id=project.id, kind="process", step="", log_path="")
        job.priority = priority
        session.add(job)
        session.flush()
        assert job.id is not None
        job_id = job.id
        job.log_path = str(job_dir(job_id) / JOB_LOG)
        session.commit()
    return job_id


def run_process_job(
    engine: Engine,
    job_id: int,
    *,
    llm: LLMClient | None = None,
    transcript: Path | None = None,
) -> list[Clip]:
    """Run process job job_id and return its project's new clips, best first.

    Runs the steps of STEP_NAMES (run_step), then saves, reframes and
    renders the clips of snapped.json (process_clips.make_clips). A step or
    stage that an earlier run of the job finished (its marker,
    pipeline/step.step_done) is skipped, so a job that restarts resumes
    where it stopped; the clips of an earlier run that did not save them
    all are deleted first. llm, if set, replaces the configured LLM in
    curate; transcript, if set, is a transcript.json that is copied into
    the work directory, so transcribe skips its work. The job and its
    project are running, then done; a clip that fails to render is failed,
    but the job is still done. If anything else fails, the job and project
    are failed with the error, and the error is raised again: a StepError
    or FFmpegError if a step cannot finish.
    """
    job, project = start_job(engine, job_id)
    work = job_dir(job_id)
    try:
        with job_log(Path(job.log_path)):
            finished = done_steps(work)
            if finished:
                logger.info("job %d resumes; finished: %s", job_id, finished)
            clear_unsaved_clips(engine, job.project_id, work)
            if transcript is not None and not step_done(work, "transcribe"):
                work.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(transcript, work / TRANSCRIPT)
            for name in STEP_NAMES:
                if step_done(work, name):
                    logger.info("job %d: %s finished before; skipping it", job_id, name)
                else:
                    run_step(engine, name, job_id, llm=llm)
                if name == "ingest":
                    _describe_project(engine, job_id, work)
            clips = make_clips(engine, job_id, job.project_id, project.settings, work)
    except Exception as exc:
        _finish(engine, job_id, "failed", error=str(exc))
        raise
    _finish(engine, job_id, "done")
    return clips


def run_step(
    engine: Engine,
    name: str,
    job_id: int,
    *,
    force: bool = False,
    llm: LLMClient | None = None,
    work: Path | None = None,
    processing: ProcessingSettings | None = None,
    ranges: tuple[tuple[float, float], ...] = (),
) -> Path:
    """Run the step called name for job job_id and return its output path.

    The step reads the source and settings of the job's project and works in
    {data_dir}/work/{job_id}; llm, if set, is the LLM that curate asks. work
    and processing, if set, replace that directory and those settings (a
    reprompt job works in its project's process directory, reprompt);
    ranges restrict curate to those source-second ranges (StepSettings).
    Job.step is set to name and Job.progress follows the step from 0 to 1;
    Job.status is left to the caller. When the step has finished, its
    marker is written (pipeline/step.mark_done). Raises StepError if the
    job does not exist.
    """
    with Session(engine) as session:
        job, project = load_job(session, job_id)
        project_id = project.id
        settings = StepSettings(
            source=project.source_url or project.source_path,
            processing=project.settings if processing is None else processing,
            on_progress=progress_writer(engine, job_id),
            llm=llm,
            ranges=ranges,
        )
        record_progress(session, job, name, 0.0)
        session.commit()

    work = job_dir(job_id) if work is None else work
    output = load_step(name)(work, settings, force=force)
    if name == "transcribe" and project_id is not None:
        index_quietly(engine, project_id, work)
    if force or not step_done(work, name):
        mark_done(work, name)
    save_progress(engine, job_id, 1.0)
    return output


def start_job(engine: Engine, job_id: int) -> tuple[JobRow, ProjectRow]:
    """Mark job job_id and its project running; return their (detached) rows."""
    with Session(engine, expire_on_commit=False) as session:
        job, project = load_job(session, job_id)
        job.status = project.status = "running"
        job.error = None
        session.add_all([job, project])
        session.commit()
    return job, project


def _finish(
    engine: Engine, job_id: int, status: JobStatus, *, error: str | None = None
) -> None:
    """Set the status of job job_id and its project, and the job's error.
    A done project is announced (webhook, notification) and gets its
    autopilot drafts (autopilot.pipeline.drafts_after_job); a failed one
    may stop its campaign's autopilot (autopilot.safety.after_failed_job)."""
    with Session(engine) as session:
        job, project = load_job(session, job_id)
        job.status = project.status = status
        job.error = error
        if status == "done":
            job.overall_progress = project.overall_progress = 1.0
            job.eta_seconds = project.eta_seconds = None
        project_id = project.id
        session.add_all([job, project])
        session.commit()
    job_progress.etas.forget(job_id)
    if status == "done" and project_id is not None:
        webhook_events.project_completed(engine, project_id)
        notifications.project_done(engine, project_id)
        drafts_after_job(engine, project_id)
    if status == "failed" and project_id is not None:
        safety.after_failed_job(engine, project_id)


def _describe_project(engine: Engine, job_id: int, work: Path) -> None:
    """Copy the title and duration that ingest found, and the path of its
    thumbnail, to the project of job job_id; a title the owner already gave
    the project (a rename while it waited) is kept."""
    meta = load_meta(work)
    with Session(engine) as session:
        _, project = load_job(session, job_id)
        project.title = project.title or meta.title
        project.duration = meta.duration
        project.thumbnail_path = str(work / THUMB)
        session.add(project)
        session.commit()
