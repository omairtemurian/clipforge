"""Tests for migration 031_v2_search: it adds the empty FTS5 index and its
state table, keeps the v1 data as it was, and deleting a project removes
its rows of the index and its state."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import migrate
from clipforge.search.fts import fts5_available
from clipforge.search.rows import SearchStateRow
from sqlalchemy import Engine
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def columns(rows: Rows, table: str) -> list[str]:
    return [row[1] for row in rows(f"SELECT * FROM pragma_table_info('{table}')")]


def test_the_bundled_sqlite_has_fts5(blank_engine: Engine) -> None:
    assert fts5_available(blank_engine)


def test_the_search_tables_are_added_empty(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 30))
    projects = rows("SELECT * FROM project")
    clips = rows("SELECT * FROM clip")

    assert migrate(blank_engine, migrations_through(tmp_path, 31)) == [31]

    assert rows("SELECT * FROM project") == projects
    assert rows("SELECT * FROM clip") == clips
    assert rows("SELECT * FROM search_fts") == []
    assert rows("SELECT * FROM search_state") == []
    assert columns(rows, "search_state") == [
        column.name for column in SearchStateRow.__table__.columns
    ]
    assert columns(rows, "search_fts") == [
        "text",
        "project_id",
        "segment_id",
        "start",
        "end",
    ]


def test_deleting_a_project_removes_its_index(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    first, _, _ = seed_v1(blank_engine)
    project = rows(f"SELECT project_id FROM clip WHERE id = {first}")[0][0]
    migrate(blank_engine, migrations_through(tmp_path, 31))
    with blank_engine.begin() as conn:
        for owner in (project, project + 1000):
            conn.exec_driver_sql(
                'INSERT INTO search_fts (text, project_id, segment_id, start, "end") '
                f"VALUES ('hello there', {owner}, 0, 1.5, 2.5)"
            )
        conn.exec_driver_sql(
            "INSERT INTO search_state VALUES "
            f"({project}, 1, 2, 1, '2026-01-01 00:00:00.000000')"
        )

    with blank_engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM project WHERE id = {project}")

    assert rows("SELECT project_id FROM search_fts") == [(project + 1000,)]
    assert rows("SELECT * FROM search_state") == []
