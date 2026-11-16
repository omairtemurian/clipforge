"""Tests for migration 017_v2_campaign_watch: watched channels and projects
made before keep their data and get no campaign and no publication date."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import migrate
from sqlalchemy import Engine
from test_migration_v2_watch import CHANNEL
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_channels_and_projects_get_no_campaign(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 16))
    with blank_engine.begin() as conn:
        conn.exec_driver_sql(CHANNEL)
    channels = rows("SELECT * FROM watched_channel")
    projects = rows("SELECT * FROM project")
    assert projects

    assert migrate(blank_engine, migrations_through(tmp_path, 17)) == [17]

    assert [r[:-1] for r in rows("SELECT * FROM watched_channel")] == channels
    assert [r[:-1] for r in rows("SELECT * FROM project")] == projects
    assert rows("SELECT campaign_id FROM watched_channel") == [(None,)]
    assert rows("SELECT source_published_at FROM project") == [(None,)] * len(projects)
