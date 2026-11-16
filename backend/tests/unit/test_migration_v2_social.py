"""Tests for migration 018_v2_social: it adds the social_account and post
tables and leaves the v1 data as it was."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import migrate
from sqlalchemy import Engine
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_social_tables_are_added_next_to_the_existing_data(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 17))
    projects = rows("SELECT * FROM project")
    clips = rows("SELECT * FROM clip")
    assert projects and clips

    assert migrate(blank_engine, migrations_through(tmp_path, 18)) == [18]

    assert rows("SELECT * FROM project") == projects
    assert rows("SELECT * FROM clip") == clips
    assert rows("SELECT count(*) FROM social_account") == [(0,)]
    assert rows("SELECT count(*) FROM post") == [(0,)]
    foreign_keys = rows(
        'SELECT "from", "table", on_delete FROM pragma_foreign_key_list(\'post\')'
    )
    assert set(foreign_keys) == {
        ("clip_id", "clip", "CASCADE"),
        ("account_id", "social_account", "SET NULL"),
        ("thumbnail_asset_id", "asset", "SET NULL"),
    }
