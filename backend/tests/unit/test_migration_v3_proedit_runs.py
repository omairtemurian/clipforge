"""Tests for migration 040_proedit_runs: a Pro Edit run gets its job, mode,
options and notes; the runs that exist keep their data and get mode
"start", no options and no notes."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import JobRow, migrate
from clipforge.models import ProEditOptions
from clipforge.proedit.rows import ProEditRunRow
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_runs_get_the_defaults(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 39))
    clip_id = rows("SELECT id FROM clip")[0][0]
    with blank_engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO pro_edit_run (clip_id, status, rounds, critic_scores) "
            f"VALUES ({clip_id}, 'done', 0, '[]')"
        )
    runs = rows("SELECT * FROM pro_edit_run")

    assert migrate(blank_engine, migrations_through(tmp_path, 40)) == [40]

    after = rows("SELECT * FROM pro_edit_run")
    assert [row[:-4] for row in after] == runs
    assert [row[-4:] for row in after] == [(None, "start", None, "[]")]
    migrate(blank_engine)
    with Session(blank_engine) as session:
        run = session.get(ProEditRunRow, after[0][0])
        assert run is not None
        model = run.to_model()
        assert (model.job_id, model.mode, model.options, model.notes) == (
            None,
            "start",
            None,
            [],
        )


def test_a_run_keeps_its_job_options_and_notes(engine: Engine) -> None:
    project_id = add_project(engine)
    clip_id = add_clip(engine, project_id, "candidate", 50)
    options = ProEditOptions(preset="phonk_edit", intensity="pro", use_critic=False)
    with Session(engine) as session:
        job = JobRow(
            project_id=project_id, clip_id=clip_id, kind="proedit", step="plan",
            log_path="job.log",
        )  # fmt: skip
        session.add(job)
        session.commit()
        run = ProEditRunRow(
            clip_id=clip_id, job_id=job.id, mode="regenerate", options=options,
            notes=["the LLM is off"],
        )  # fmt: skip
        session.add(run)
        session.commit()
        saved = run.to_model()
        assert (saved.job_id, saved.mode, saved.options, saved.notes) == (
            job.id,
            "regenerate",
            options,
            ["the LLM is off"],
        )
        session.delete(job)
        session.commit()
        session.refresh(run)
        assert run.job_id is None
