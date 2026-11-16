"""Pieces of the automation loop tests (tests only): a processed project with
a candidate clip, and what the render job leaves behind."""

from pathlib import Path

from clipforge.db import ClipRow
from clipforge.pipeline.render import clip_output
from seed import add_clip, add_project, add_work
from social_fakes import set_rights, write_video
from sqlalchemy import Engine
from sqlmodel import Session


def processed_clip(engine: Engine, sample_mp4: Path) -> tuple[int, int]:
    """Add a processed project with source rights and a candidate clip;
    return (project id, clip id)."""
    project_id = add_project(engine)
    add_work(engine, project_id, sample_mp4)
    set_rights(engine, project_id, "own")
    return project_id, add_clip(engine, project_id, "candidate", 82, "Pizza")


def finish_render(engine: Engine, project_id: int, clip_id: int) -> None:
    """Do what the render job would: the clip's video and rendered status."""
    output = clip_output(project_id, clip_id)
    write_video(output)
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        row.status = "rendered"
        row.output_path = str(output)
        session.commit()
