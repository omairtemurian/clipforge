"""Tests for migration 013_v2_channels: Auto Import's watched_channel and
watched_video tables; v1 data is kept."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clipforge.db import migrate
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]
CHANNEL = (
    "INSERT INTO watched_channel (channel_id, title, settings, credit_line,"
    " auto_schedule_drafts, enabled, created_at)"
    " VALUES ('UCBR8-60-B28hp2BmDPdntcQ', '', '{}', '', 0, 1, '2026-10-31')"
)
VIDEO = (
    "INSERT INTO watched_video (watched_channel_id, video_id, title, seen_at)"
    " VALUES (1, 'abc', '', '2026-10-31')"
)


def test_v1_data_is_kept_and_the_tables_start_empty(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 12))
    before = [rows(f"SELECT * FROM {t}") for t in ("project", "clip", "job")]

    assert migrate(blank_engine, migrations_through(tmp_path, 13)) == [13]

    assert [rows(f"SELECT * FROM {t}") for t in ("project", "clip", "job")] == before
    assert rows("SELECT COUNT(*) FROM watched_channel") == [(0,)]
    assert rows("SELECT COUNT(*) FROM watched_video") == [(0,)]


def test_a_channel_is_watched_once(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(CHANNEL)
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql(CHANNEL)


def test_a_video_is_recorded_once_and_removed_with_its_channel(
    engine: Engine, rows: Rows
) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(CHANNEL)
        conn.exec_driver_sql(VIDEO)
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql(VIDEO)
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM watched_channel")

    assert rows("SELECT COUNT(*) FROM watched_video") == [(0,)]
