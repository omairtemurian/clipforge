"""Tests for migration 014_v2_watch: the push state of the watched channels
(existing channels start off), the watched_streamer and watch_event tables;
a streamer is watched once and an alert is recorded once."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clipforge.db import migrate
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from v1db import migrations_through

Rows = Callable[[str], list[tuple[Any, ...]]]
CHANNEL = (
    "INSERT INTO watched_channel (channel_id, title, settings, credit_line,"
    " auto_schedule_drafts, enabled, created_at)"
    " VALUES ('UCBR8-60-B28hp2BmDPdntcQ', 'YouTube', '{}', '', 0, 1, '2026-10-31')"
)
STREAMER = (
    "INSERT INTO watched_streamer (login, display_name, enabled, push_state,"
    " created_at) VALUES ('afro', 'Afro', 1, 'off', '2026-10-31')"
)
EVENT = (
    "INSERT INTO watch_event (platform, kind, external_id, source_name, title,"
    " url, detected_at, via) VALUES ('twitch', 'live', '409', 'Afro', '', '',"
    " '2026-10-31', 'poll')"
)


def test_existing_channels_start_with_the_push_off(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate(blank_engine, migrations_through(tmp_path, 13))
    with blank_engine.begin() as conn:
        conn.exec_driver_sql(CHANNEL)

    assert migrate(blank_engine, migrations_through(tmp_path, 14)) == [14]

    assert rows(
        "SELECT title, push_state, push_lease_expires_at, push_requested_at,"
        " push_error FROM watched_channel"
    ) == [("YouTube", "off", None, None, None)]
    assert rows("SELECT COUNT(*) FROM watched_streamer") == [(0,)]
    assert rows("SELECT COUNT(*) FROM watch_event") == [(0,)]


@pytest.mark.parametrize("insert", [STREAMER, EVENT], ids=["streamer", "event"])
def test_a_streamer_and_an_alert_are_recorded_once(engine: Engine, insert: str) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(insert)
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql(insert)
