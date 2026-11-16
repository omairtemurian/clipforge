"""Tests for migration 020_v2_api_keys: it adds the empty api_key table,
whose columns are the ApiKeyRow's, and keeps the v1 data as it was."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.api_keys import ApiKeyRow
from clipforge.db import migrate
from sqlalchemy import Engine
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_the_api_key_table_is_added_empty(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 19))
    projects = rows("SELECT * FROM project")
    clips = rows("SELECT * FROM clip")

    assert migrate(blank_engine, migrations_through(tmp_path, 20)) == [20]

    assert rows("SELECT * FROM project") == projects
    assert rows("SELECT * FROM clip") == clips
    assert rows("SELECT * FROM api_key") == []
    columns = [row[1] for row in rows("SELECT * FROM pragma_table_info('api_key')")]
    assert columns == [column.name for column in ApiKeyRow.__table__.columns]
    unique = rows("SELECT * FROM pragma_index_list('api_key') WHERE \"unique\" = 1")
    assert len(unique) == 1
