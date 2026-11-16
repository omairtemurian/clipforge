"""Tests for migration 012_inbox_import: the table of imported files."""

from collections.abc import Callable
from typing import Any

import pytest
from clipforge.inbox_watch import InboxImportRow
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

Rows = Callable[[str], list[tuple[Any, ...]]]
INSERT = (
    "INSERT INTO inbox_import (path, size, mtime_ns, project_id, imported_at)"
    " VALUES ('/in/a.mp4', 10, 5, 1, '2026-10-31 10:00:00')"
)


def test_the_table_has_the_columns_of_the_row_class(engine: Engine, rows: Rows) -> None:
    columns = [(r[1], r[2], r[5]) for r in rows("PRAGMA table_info(inbox_import)")]

    assert [name for name, _, _ in columns] == [
        c.name for c in InboxImportRow.__table__.columns
    ]
    assert {name for name, _, key in columns if key} == {"path", "size", "mtime_ns"}


def test_a_file_is_recorded_once_per_path_size_and_mtime(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(INSERT)
        conn.exec_driver_sql(INSERT.replace("10, 5", "11, 5"))
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql(INSERT)
