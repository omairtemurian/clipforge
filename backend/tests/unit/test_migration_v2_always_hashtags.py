"""Tests for migration 028_v2_always_hashtags: an account has an empty list of
always-included hashtags and keeps its data."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import migrate
from sqlalchemy import Engine
from v1db import migrate_to_v1, migrations_through

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_accounts_get_no_always_hashtags(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    migrate(blank_engine, migrations_through(tmp_path, 27))
    with blank_engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO social_account (platform, external_id, display_name, "
            "token_ref, scopes, connected_at, restrictions) VALUES "
            "('tiktok', 'a', 'A', 'ref-a', '[]', '2030-01-01 00:00:00', '[]')"
        )

    assert migrate(blank_engine, migrations_through(tmp_path, 28)) == [28]

    assert rows("SELECT external_id, always_hashtags FROM social_account") == [
        ("a", "[]")
    ]
