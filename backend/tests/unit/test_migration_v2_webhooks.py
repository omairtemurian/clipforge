"""Tests for migration 021_v2_webhooks: it adds the empty webhook and
webhook_delivery tables, whose columns are the rows' (a deleted webhook takes
its deliveries along), and keeps the v1 data as it was."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import migrate
from clipforge.webhook_rows import WebhookDeliveryRow, WebhookRow
from sqlalchemy import Engine
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def columns(rows: Rows, table: str) -> list[str]:
    return [row[1] for row in rows(f"SELECT * FROM pragma_table_info('{table}')")]


def test_the_webhook_tables_are_added_empty(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 20))
    projects = rows("SELECT * FROM project")
    clips = rows("SELECT * FROM clip")

    assert migrate(blank_engine, migrations_through(tmp_path, 21)) == [21]

    assert rows("SELECT * FROM project") == projects
    assert rows("SELECT * FROM clip") == clips
    assert rows("SELECT * FROM webhook") == []
    assert rows("SELECT * FROM webhook_delivery") == []
    assert columns(rows, "webhook") == [c.name for c in WebhookRow.__table__.columns]
    assert columns(rows, "webhook_delivery") == [
        c.name for c in WebhookDeliveryRow.__table__.columns
    ]


def test_deleting_a_webhook_deletes_its_deliveries(engine: Engine, rows: Rows) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO webhook (url, events, secret_enc, enabled, created_at) "
            "VALUES ('https://x.test', '[]', 's', 1, '2030-01-01 00:00:00')"
        )
        conn.exec_driver_sql(
            "INSERT INTO webhook_delivery (webhook_id, event, data, status, "
            "attempts, created_at) VALUES (1, 'clip.rendered', '{}', 'pending', 0, "
            "'2030-01-01 00:00:00')"
        )
        conn.exec_driver_sql("DELETE FROM webhook WHERE id = 1")

    assert rows("SELECT * FROM webhook_delivery") == []
