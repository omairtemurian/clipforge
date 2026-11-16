"""The clip stages of a process job, after snap: save, reframe and render.

The clips that score kept and snap cut between words (snapped.json) become
the project's clips (SPEC 6.7), which are reframed (their
crop_<clip_id>.json, SPEC 6.8), take their layouts as the project's default
layout says (clip_layouts) and are rendered (clipforge.clips). Each stage
is resumable (SPEC-v2 2.2): the saved clips and the planned layouts leave a
stage marker (pipeline/step.mark_done), reframe keeps the crop plans it
already wrote and a clip that is already rendered is not rendered again, so
a job that restarts goes on where it stopped.
"""

import logging
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, delete, select

from clipforge.campaign_presets import preset_new_clips
from clipforge.clip_layouts import set_planned_layouts
from clipforge.clips import render_clip_row, save_clips
from clipforge.db import ClipRow
from clipforge.job_rows import progress_writer, save_progress, set_step
from clipforge.models import Clip, ProcessingSettings, ScoredList
from clipforge.pipeline.reframe import ClipSpan
from clipforge.pipeline.reframe_run import reframe_clips
from clipforge.pipeline.step import (
    SNAPPED,
    load_json,
    mark_done,
    step_done,
)

logger = logging.getLogger(__name__)

# The stage that saves snapped.json as the project's clips (a marker only).
CLIPS_STAGE = "clips"
# Job.step while the clips are reframed, then rendered.
REFRAME_STEP = "reframe"
RENDER_STEP = "render"


def clear_unsaved_clips(engine: Engine, project_id: int, work: Path) -> None:
    """Delete the first-set clips of project project_id unless its job, in
    work, has saved them (CLIPS_STAGE): those of a run that stopped before
    they were all saved must not stay, since the job saves them afresh.
    The clips of reprompt result sets are never touched."""
    if step_done(work, CLIPS_STAGE):
        return
    with Session(engine) as session:
        session.exec(
            delete(ClipRow).where(
                col(ClipRow.project_id) == project_id, col(ClipRow.result_set) == 1
            )
        )
        session.commit()


def make_clips(
    engine: Engine,
    job_id: int,
    project_id: int,
    processing: ProcessingSettings,
    work: Path,
) -> list[Clip]:
    """Save, reframe and render the clips of job job_id, whose project is
    project_id and work directory work; return them, best first.

    A stage that an earlier run of the job finished is skipped. Job.step is
    REFRAME_STEP, then RENDER_STEP, while those stages run.
    """
    spans = _saved_clips(engine, project_id, processing, work)
    clip_ids = [span.clip_id for span in spans]
    if not step_done(work, REFRAME_STEP):
        set_step(engine, job_id, REFRAME_STEP)
        on_progress = progress_writer(engine, job_id)
        reframe_clips(
            work,
            spans,
            processing.aspect,
            preset=processing.reframe_preset,
            camera_motion=processing.camera_motion,
            on_progress=on_progress,
        )
        set_planned_layouts(
            engine,
            work,
            clip_ids,
            processing.default_layout,
            processing.zoom_out_moments,
        )
        mark_done(work, REFRAME_STEP)
    clips = render_clips(engine, job_id, clip_ids, work)
    log_outcome(job_id, clips)
    return clips


def _saved_clips(
    engine: Engine, project_id: int, processing: ProcessingSettings, work: Path
) -> list[ClipSpan]:
    """Return the spans of the project's clips, best first, after saving
    the clips of snapped.json, with the preset of the project's campaign
    (campaign_presets), if no earlier run of the job did (CLIPS_STAGE)."""
    if not step_done(work, CLIPS_STAGE):
        kept = load_json(work / SNAPPED, ScoredList, "snap").clips
        clip_ids = save_clips(engine, project_id, kept, processing, work)
        preset_new_clips(engine, project_id, clip_ids)
        mark_done(work, CLIPS_STAGE)
    with Session(engine) as session:
        rows = session.exec(
            select(ClipRow)
            .where(ClipRow.project_id == project_id, ClipRow.result_set == 1)
            .order_by(col(ClipRow.id))
        ).all()
        models = [row.to_model() for row in rows]
    return [ClipSpan(clip.id, clip.start, clip.end) for clip in models]


def render_clips(
    engine: Engine, job_id: int, clip_ids: Sequence[int], work: Path
) -> list[Clip]:
    """Render the clips clip_ids from the job's work directory, work, in
    order and return them.

    A clip that is rendered, with its video on disk, is kept as it is.
    Job.step is RENDER_STEP and Job.progress the fraction of clips done.
    """
    set_step(engine, job_id, RENDER_STEP)
    clips = []
    for done, clip_id in enumerate(clip_ids, start=1):
        rendered = _rendered(engine, clip_id)
        if rendered is not None:
            logger.info("clip %d is rendered already; keeping it", clip_id)
            clips.append(rendered)
        else:
            clips.append(render_clip_row(engine, clip_id, work))
        save_progress(engine, job_id, round(done / len(clip_ids), 2))
    save_progress(engine, job_id, 1.0)
    return clips


def _rendered(engine: Engine, clip_id: int) -> Clip | None:
    """Return clip clip_id if it is rendered and its video exists, else None."""
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        if row is None or row.status != "rendered" or not row.output_path:
            return None
        if not Path(row.output_path).is_file():
            return None
        return row.to_model()


def log_outcome(job_id: int, clips: Sequence[Clip]) -> None:
    """Log how many of the job's clips were rendered and how many failed."""
    if not clips:
        logger.warning("job %d found no clips in the video", job_id)
        return
    failed = sum(clip.status == "failed" for clip in clips)
    logger.log(
        logging.WARNING if failed else logging.INFO,
        "job %d rendered %d of %d clips; %d failed",
        job_id,
        len(clips) - failed,
        len(clips),
        failed,
    )
