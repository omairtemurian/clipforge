"""Tests for migration 032_v2_archive: it adds the project's archived_at
column, NULL for the projects that exist, and keeps their data."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import ProjectRow, migrate
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_projects_are_not_archived(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 31))
    projects = rows("SELECT * FROM project")

    assert migrate(blank_engine, migrations_through(tmp_path, 32)) == [32]

    after = rows("SELECT * FROM project")
    assert [row[:-1] for row in after] == projects
    assert [row[-1] for row in after] == [None] * len(projects)
    migrate(blank_engine)
    with Session(blank_engine) as session:
        project = session.get(ProjectRow, after[0][0])
        assert project is not None
        assert project.to_model().archived_at is None
