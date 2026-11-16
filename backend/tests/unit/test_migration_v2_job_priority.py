"""Tests for migration 006_v2_job_priority: the job's priority column, with
priority 0 for the jobs of earlier versions, and its claim index."""

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


def test_v1_jobs_get_priority_zero_and_keep_their_fields(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    with blank_engine.begin() as conn:
        conn.exec_driver_sql(QUEUED_JOB)
    before = rows("SELECT * FROM job ORDER BY id")

    assert migrate(blank_engine, migrations_through(tmp_path, 6)) == [4, 5, 6]

    after = rows("SELECT * FROM job ORDER BY id")
    assert after == [(*row, 0) for row in before]
    names = [row[1] for row in rows("PRAGMA table_info(job)")]
    assert names[-1] == "priority"
    assert rows("SELECT kind, status, priority FROM job ORDER BY id") == [
        ("render", "done", 0),
        ("process", "queued", 0),
    ]


def test_the_claim_index_covers_status_and_priority(engine: Engine, rows: Rows) -> None:
    assert rows("SELECT name FROM pragma_index_info('ix_job_status_priority')") == [
        ("status",),
        ("priority",),
    ]
