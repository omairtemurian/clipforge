"""Tests for migration 007_v2_job_attempts: a job's attempts, one for the
v1 jobs that a worker started and none for the queued ones."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import migrate
from sqlalchemy import Engine
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]

QUEUED_JOB = (
    "INSERT INTO job (project_id, clip_id, kind, step, progress, status,"
    " log_path) VALUES (1, NULL, 'process', '', 0.0, 'queued', 'q.log')"
)


def test_started_v1_jobs_get_one_attempt_and_queued_ones_none(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    with blank_engine.begin() as conn:
        conn.exec_driver_sql(QUEUED_JOB)
    migrate(blank_engine, migrations_through(tmp_path, 6))
    before = rows("SELECT * FROM job ORDER BY id")

    assert migrate(blank_engine, migrations_through(tmp_path, 7)) == [7]

    after = rows("SELECT * FROM job ORDER BY id")
    assert after == [(*row, 1 if row[6] != "queued" else 0) for row in before]
    assert [row[6] for row in before] == ["done", "queued"]
    names = [row[1] for row in rows("PRAGMA table_info(job)")]
    assert names[-1] == "attempts"
