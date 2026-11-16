"""Tests for migration 036_v2_autopilot_pause: it adds the empty
autopilot_pause table, whose columns are the row's, keeps the data as it was
and allows only the one row of the global pause."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clipforge.autopilot.rows import AutopilotPauseRow
from clipforge.db import migrate
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_the_table_is_added_empty(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 35))
    projects = rows("SELECT * FROM project")

    assert migrate(blank_engine, migrations_through(tmp_path, 36)) == [36]

    assert rows("SELECT * FROM project") == projects
    assert rows("SELECT * FROM autopilot_pause") == []
    names = [c[1] for c in rows("SELECT * FROM pragma_table_info('autopilot_pause')")]
    assert names == [column.name for column in AutopilotPauseRow.__table__.columns]


def test_only_the_one_pause_row_is_allowed(engine: Engine, rows: Rows) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO autopilot_pause (id, paused_at) "
            "VALUES (1, '2030-01-01 00:00:00')"
        )
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO autopilot_pause (id, paused_at) "
            "VALUES (2, '2030-01-01 00:00:00')"
        )
    assert rows("SELECT id FROM autopilot_pause") == [(1,)]
