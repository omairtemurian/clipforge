"""Reprompt (SPEC-v2 3.2): new clips for a finished project from a new prompt,
without ingesting, transcribing or analysing the video again.

enqueue_reprompt queues a "reprompt" job with the new prompt (saved as
prompt.txt in the job's work directory). run_reprompt_job then runs only
curate, score and snap again (after visuals, which adds the clip-anything
files a clip-anything reprompt lacks), in the work directory of the project's process
job (the transcript, signals and enriched.txt are read from there), with the
prompt as the project's keyword_prompt and the clipping mode "ai". Their
clips become the project's next result set (Clip.result_set), which is
reframed and rendered like the first one. The clips of the earlier sets are
kept as they are; the project's current set (Project.result_set) changes only
when the new set is complete, so a reprompt that fails leaves the project as
it was. A reprompt that is stopped and started again begins at curate: it
deletes its unfinished clips first.

Clip by topic (pipeline/chapters) is a reprompt with ranges: the source-second
ranges of the chosen chapters, saved as ranges.json in the job's directory,
to which curate is restricted. Its prompt is optional; without one the clips
are the best of the chapters.
"""

import json
import logging
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select, update

from clipforge import notifications, webhook_events
from clipforge.campaign_presets import preset_new_clips
from clipforge.clip_layouts import set_planned_layouts
from clipforge.clips import save_clips
from clipforge.db import ClipRow, JobRow, ProjectRow
from clipforge.job_rows import process_work_dir, progress_writer, set_step
from clipforge.joblog import job_log
from clipforge.llm import LLMClient
from clipforge.models import Clip, ProcessingSettings, ScoredList
from clipforge.pipeline.reframe import ClipSpan
from clipforge.pipeline.reframe_run import reframe_clips
from clipforge.pipeline.step import ENRICHED, SNAPPED, StepError, job_dir, load_json
from clipforge.process import JOB_LOG, run_step, start_job
from clipforge.process_clips import REFRAME_STEP, log_outcome, render_clips

logger = logging.getLogger(__name__)

PROMPT_FILE = "prompt.txt"
RANGES_FILE = "ranges.json"
# The steps that a reprompt runs again, in order. Visuals only does what
# the process job did not (clip anything was off or another clipping mode).
REPROMPT_STEPS = ("visuals", "curate", "score", "snap")


class RepromptRefused(Exception):
    """The project cannot be reprompted now; the message says why."""


def enqueue_reprompt(
    engine: Engine,
    project_id: int,
    prompt: str | None,
    ranges: Sequence[tuple[float, float]] = (),
) -> int:
    """Queue a reprompt job of project project_id with prompt, restricted to
    ranges of source seconds if any; return its id. prompt may be None only
    with ranges.

    The project is queued meanwhile (a second reprompt is refused). Raises
    RepromptRefused unless the project is done and its process job's work
    directory still holds the enriched transcript, and StepError if the
    project does not exist or has no process job.
    """
    with Session(engine) as session:
        if session.get(ProjectRow, project_id) is None:
            raise StepError(f"project {project_id} not found")
        work = process_work_dir(session, project_id)
    if not (work / ENRICHED).is_file():
        raise RepromptRefused(
            f"project {project_id} has no transcript to ask again: process it first"
        )
    with engine.begin() as conn:
        claimed = conn.execute(
            update(ProjectRow)
            .where(col(ProjectRow.id) == project_id, col(ProjectRow.status) == "done")
            .values(status="queued")
        )
        if claimed.rowcount != 1:
            raise RepromptRefused(
                f"project {project_id} is not finished; reprompt it when it is done"
            )
    with Session(engine) as session:
        job = JobRow(project_id=project_id, kind="reprompt", step="", log_path="")
        session.add(job)
        session.flush()
        assert job.id is not None
        job.log_path = str(job_dir(job.id) / JOB_LOG)
        session.commit()
        job_id = job.id
    job_dir(job_id).mkdir(parents=True, exist_ok=True)
    if prompt is not None:
        (job_dir(job_id) / PROMPT_FILE).write_text(prompt, encoding="utf-8")
    if ranges:
        (job_dir(job_id) / RANGES_FILE).write_text(json.dumps(ranges), encoding="utf-8")
    return job_id


def run_reprompt_job(
    engine: Engine, job_id: int, *, llm: LLMClient | None = None
) -> list[Clip]:
    """Run reprompt job job_id and return the clips of its new result set,
    best first.

    Runs curate, score and snap again (run_step, forced), after visuals
    (not forced: it only adds the clip-anything files missing), with the job's
    prompt, then saves, reframes and renders the clips of snapped.json as
    result set Project.result_set + 1, which then becomes the project's
    current set. A clip that fails to render is failed, but the job is still
    done. If anything fails, the new clips are deleted, the project is done
    again with its old set, the job is failed with the error, and the error
    is raised again.
    """
    job, project = start_job(engine, job_id)
    work = _process_work(engine, job.project_id)
    new_set = project.result_set + 1
    try:
        with job_log(Path(job.log_path)):
            prompt, ranges = _read_request(job_id)
            processing = project.settings.model_copy(
                update={"keyword_prompt": prompt, "clipping": "ai"}
            )
            _drop_set(engine, job.project_id, new_set)
            logger.info(
                "job %d reprompts project %d: %r in %s",
                job_id,
                project.id,
                prompt,
                list(ranges) or "the whole video",
            )
            for name in REPROMPT_STEPS:
                run_step(
                    engine,
                    name,
                    job_id,
                    force=name != "visuals",
                    llm=llm,
                    work=work,
                    processing=processing,
                    ranges=ranges,
                )
            clips = _make_set(engine, job_id, job.project_id, processing, work, new_set)
    except Exception as exc:
        _drop_set(engine, job.project_id, new_set)
        _finish(engine, job_id, error=str(exc))
        raise
    _finish(engine, job_id, processing=processing, result_set=new_set)
    return clips


def restore_project(session: Session, project_id: int) -> None:
    """Make project project_id done again with its current result set, after
    a reprompt of it failed or was given up (jobs); the caller commits."""
    project = session.get(ProjectRow, project_id)
    if project is None:
        return
    delete_set(session, project_id, project.result_set + 1)
    project.status = "done"
    project.overall_progress, project.eta_seconds = 1.0, None
    session.add(project)


def _make_set(
    engine: Engine,
    job_id: int,
    project_id: int,
    processing: ProcessingSettings,
    work: Path,
    result_set: int,
) -> list[Clip]:
    """Save, reframe and render the clips of snapped.json in work as result
    set result_set of the project; return them, best first."""
    kept = load_json(work / SNAPPED, ScoredList, "snap").clips
    clip_ids = save_clips(engine, project_id, kept, processing, work, result_set)
    preset_new_clips(engine, project_id, clip_ids)
    with Session(engine) as session:
        rows = session.exec(
            select(ClipRow)
            .where(col(ClipRow.id).in_(clip_ids))
            .order_by(col(ClipRow.id))
        ).all()
        saved = [row.to_model() for row in rows]
    spans = [ClipSpan(clip.id, clip.start, clip.end) for clip in saved]
    set_step(engine, job_id, REFRAME_STEP)
    reframe_clips(
        work,
        spans,
        processing.aspect,
        preset=processing.reframe_preset,
        camera_motion=processing.camera_motion,
        on_progress=progress_writer(engine, job_id),
    )
    set_planned_layouts(
        engine,
        work,
        clip_ids,
        processing.default_layout,
        processing.zoom_out_moments,
    )
    clips = render_clips(engine, job_id, clip_ids, work)
    log_outcome(job_id, clips)
    return sorted(clips, key=lambda clip: (-clip.scores.overall, clip.id))


def delete_set(session: Session, project_id: int, result_set: int) -> None:
    """Delete the clips of result set result_set of the project, and their
    rendered videos: the leftovers of a reprompt that did not finish (the
    caller commits)."""
    rows = session.exec(
        select(ClipRow).where(
            ClipRow.project_id == project_id, ClipRow.result_set == result_set
        )
    ).all()
    for row in rows:
        if row.output_path:
            Path(row.output_path).unlink(missing_ok=True)
        session.delete(row)


def _drop_set(engine: Engine, project_id: int, result_set: int) -> None:
    """Delete result set result_set of the project (delete_set) and commit."""
    with Session(engine) as session:
        delete_set(session, project_id, result_set)
        session.commit()


def _finish(
    engine: Engine,
    job_id: int,
    *,
    error: str | None = None,
    processing: ProcessingSettings | None = None,
    result_set: int | None = None,
) -> None:
    """End job job_id: failed with error, or done, in which case the project
    takes processing as its settings and result_set as its current set. The
    project is done either way."""
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        assert job is not None
        project = session.get(ProjectRow, job.project_id)
        assert project is not None
        job.status = "failed" if error is not None else "done"
        job.error = error
        project.status = "done"
        project.overall_progress, project.eta_seconds = 1.0, None
        if error is None:
            job.overall_progress, job.eta_seconds = 1.0, None
        if processing is not None and result_set is not None:
            project.settings, project.result_set = processing, result_set
        session.add_all([job, project])
        session.commit()
        project_id = project.id
    if error is None and project_id is not None:
        webhook_events.project_completed(engine, project_id)
        notifications.project_done(engine, project_id)


def _process_work(engine: Engine, project_id: int) -> Path:
    """Return the work directory of the project's process job."""
    with Session(engine) as session:
        return process_work_dir(session, project_id)


def _read_request(job_id: int) -> tuple[str | None, tuple[tuple[float, float], ...]]:
    """Return the prompt and the ranges that enqueue_reprompt saved for job
    job_id; raises StepError if it saved neither."""
    folder = job_dir(job_id)
    prompt = None
    if (folder / PROMPT_FILE).is_file():
        prompt = (folder / PROMPT_FILE).read_text(encoding="utf-8")
    ranges: tuple[tuple[float, float], ...] = ()
    if (folder / RANGES_FILE).is_file():
        saved = json.loads((folder / RANGES_FILE).read_text(encoding="utf-8"))
        ranges = tuple((float(start), float(end)) for start, end in saved)
    if prompt is None and not ranges:
        raise StepError(f"{folder}: the reprompt has no prompt")
    return prompt, ranges
