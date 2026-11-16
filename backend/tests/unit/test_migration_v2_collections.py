"""Tests for migration 030_v2_collections: it adds the empty collection and
collection_item tables, whose columns are the rows', keeps the v1 data as it
was, and deleting a clip or a collection removes its items."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clipforge.collection_rows import CollectionItemRow, CollectionRow
from clipforge.db import migrate
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def columns(rows: Rows, table: str) -> list[str]:
    return [row[1] for row in rows(f"SELECT * FROM pragma_table_info('{table}')")]


def test_the_collection_tables_are_added_empty(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 29))
    projects = rows("SELECT * FROM project")
    clips = rows("SELECT * FROM clip")

    assert migrate(blank_engine, migrations_through(tmp_path, 30)) == [30]

    assert rows("SELECT * FROM project") == projects
    assert rows("SELECT * FROM clip") == clips
    assert rows("SELECT * FROM collection") == []
    assert rows("SELECT * FROM collection_item") == []
    assert columns(rows, "collection") == [
        column.name for column in CollectionRow.__table__.columns
    ]
    assert columns(rows, "collection_item") == [
        column.name for column in CollectionItemRow.__table__.columns
    ]


def test_a_clip_is_in_a_collection_once_and_items_follow_their_owners(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    first, second, _ = seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 30))
    item = (
        "INSERT INTO collection_item (collection_id, clip_id, position, added_at) "
        "VALUES (1, {}, {}, '2026-01-01')"
    )
    with blank_engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO collection (name, created_at, updated_at) "
            "VALUES ('a', '2026-01-01', '2026-01-01')"
        )
        conn.exec_driver_sql(item.format(first, 0))
        conn.exec_driver_sql(item.format(second, 1))
    with pytest.raises(IntegrityError), blank_engine.begin() as conn:
        conn.exec_driver_sql(item.format(first, 2))

    with blank_engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM clip WHERE id = {first}")
    assert rows("SELECT clip_id FROM collection_item") == [(second,)]
    with blank_engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM collection")
    assert rows("SELECT * FROM collection_item") == []
    assert rows(f"SELECT id FROM clip WHERE id = {second}") == [(second,)]
