"""Seed the project and clip tables with rows for tests, and a process
job's work directory (tests only)."""

import shutil
from pathlib import Path
from typing import Any

from builders import make_clip, source_meta
from clipforge.db import ClipRow, JobRow, ProjectRow
from clipforge.models import Clip, ClipStatus, FaceBox, JobStatus, ProcessingSettings
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, crop_path, plan_crop
from clipforge.pipeline.render import clip_output
from clipforge.pipeline.step import META, SOURCE, TRANSCRIPT, job_dir, write_json
from fakes import FIXTURES
from sqlalchemy import Engine
from sqlmodel import Session


def add_project(engine: Engine) -> int:
    """Add a project of /videos/talk.mp4 and return its id."""
    with Session(engine) as session:
        project = ProjectRow(
            source_path="/videos/talk.mp4",
            title="talk",
            duration=60.0,
            thumbnail_path="",
            settings=ProcessingSettings(),
        )
        session.add(project)
        session.commit()
        assert project.id is not None
        return project.id


def add_clip(
    engine: Engine,
    project_id: int,
    status: ClipStatus,
    overall: int,
    title: str = "",
    **changes: Any,
) -> int:
    """Add make_clip's clip 10-12.5 s to project_id with status, overall score
    and title, and changes to its other fields, and return its id; a rendered
    clip gets its output_path (render.clip_output)."""
    clip = make_clip("karaoke_bold", project_id=project_id, status=status, **changes)
    fields = {name: getattr(clip, name) for name in Clip.model_fields if name != "id"}
    fields |= {
        "title": title,
        "scores": clip.scores.model_copy(update={"overall": overall}),
    }
    with Session(engine) as session:
        row = ClipRow(**fields)
        session.add(row)
        session.flush()
        assert row.id is not None
        if status == "rendered":
            row.output_path = str(clip_output(project_id, row.id))
        session.commit()
        return row.id


def add_job(
    engine: Engine,
    project_id: int,
    status: JobStatus,
    step: str = "",
    progress: float = 0.0,
) -> int:
    """Add a process job of project_id and return its id."""
    with Session(engine) as session:
        job = JobRow(
            project_id=project_id,
            kind="process",
            step=step,
            progress=progress,
            status=status,
            log_path="",
        )
        session.add(job)
        session.commit()
        assert job.id is not None
        return job.id


def add_work(engine: Engine, project_id: int, source: Path) -> Path:
    """Add a done process job of project_id whose work directory holds
    source as its source.mp4, fixtures/transcript.json and the meta.json of
    a 60 s 1280x720 video; return the directory."""
    work = job_dir(add_job(engine, project_id, "done", "render", 1.0))
    work.mkdir(parents=True)
    shutil.copy(source, work / SOURCE)
    shutil.copy(FIXTURES / TRANSCRIPT, work / TRANSCRIPT)
    write_json(work / META, source_meta())
    return work


def add_plan(work: Path, clip_id: int, start: float = 10.0, end: float = 12.5) -> None:
    """Write the 9:16 crop plan, with no faces seen, of clip clip_id from
    start to end seconds into work."""
    span = ClipSpan(clip_id, start, end)
    no_faces: list[list[FaceBox]] = [[] for _ in sample_times(start, end)]
    plan = plan_crop(span, "9:16", (1280, 720), no_faces, [])
    write_json(crop_path(work, clip_id), plan)
