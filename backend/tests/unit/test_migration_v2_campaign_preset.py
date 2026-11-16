"""Tests for migration 016_v2_campaign_preset: campaigns saved before keep
their data and get no caption template."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import migrate
from sqlalchemy import Engine
from test_migration_v2_campaigns import CAMPAIGN
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_campaigns_get_a_null_caption_template(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 15))
    with blank_engine.begin() as conn:
        conn.exec_driver_sql(CAMPAIGN)
    before = rows("SELECT * FROM campaign")

    assert migrate(blank_engine, migrations_through(tmp_path, 16)) == [16]

    after = rows("SELECT * FROM campaign")
    assert [row[:-1] for row in after] == before
    assert rows("SELECT caption_template FROM campaign") == [(None,)]
