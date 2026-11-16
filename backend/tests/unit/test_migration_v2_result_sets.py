"""Tests for migration 022_v2_result_sets: every existing project and clip is
in result set 1."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import ClipRow, ProjectRow, migrate
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_projects_and_clips_are_in_result_set_one(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    ids = seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 21))
    projects = rows("SELECT * FROM project ORDER BY id")
    clips = rows("SELECT * FROM clip ORDER BY id")

    assert migrate(blank_engine, migrations_through(tmp_path, 22)) == [22]

    assert rows("SELECT * FROM project ORDER BY id") == [(*r, 1) for r in projects]
    assert rows("SELECT * FROM clip ORDER BY id") == [(*r, 1) for r in clips]
    for table in ("project", "clip"):
        names = [row[1] for row in rows(f"PRAGMA table_info({table})")]
        assert names[-1] == "result_set"
    migrate(blank_engine)
    with Session(blank_engine) as session:
        assert [session.get_one(ClipRow, i).to_model().result_set for i in ids] == [
            1
        ] * len(ids)
        assert session.get_one(ProjectRow, 1).to_model().result_set == 1
