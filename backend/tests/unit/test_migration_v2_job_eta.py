"""Tests for migration 029_v2_job_eta: jobs and projects get an overall
progress and an ETA, and the projects that exist count as opened."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import migrate
from sqlalchemy import Engine
from v1db import V1_PROJECT, migrate_to_v1, migrations_through

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_rows_get_no_eta_and_projects_count_as_opened(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    migrate(blank_engine, migrations_through(tmp_path, 28))
    with blank_engine.begin() as conn:
        conn.exec_driver_sql(V1_PROJECT)
        conn.exec_driver_sql(
            "INSERT INTO job (project_id, kind, step, progress, status, log_path) "
            "VALUES (1, 'process', 'render', 1.0, 'done', '')"
        )

    assert migrate(blank_engine, migrations_through(tmp_path, 29)) == [29]

    assert rows("SELECT overall_progress, eta_seconds FROM job") == [(1.0, None)]
    [(overall, eta, opened)] = rows(
        "SELECT overall_progress, eta_seconds, opened_at IS NOT NULL FROM project"
    )
    assert (overall, eta, opened) == (1.0, None, 1)
