"""Tests for migration 027_v2_account_default: the oldest account of each
platform becomes its default and the rows keep their data."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import migrate
from sqlalchemy import Engine
from v1db import migrate_to_v1, migrations_through

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_each_platforms_oldest_account_becomes_its_default(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    migrate(blank_engine, migrations_through(tmp_path, 26))
    with blank_engine.begin() as conn:
        for platform, external_id in (
            ("tiktok", "a"),
            ("youtube", "b"),
            ("tiktok", "c"),
        ):
            conn.exec_driver_sql(
                "INSERT INTO social_account (platform, external_id, display_name, "
                "token_ref, scopes, connected_at, restrictions) VALUES "
                f"('{platform}', '{external_id}', '{external_id}', "
                f"'ref-{external_id}', '[]', '2030-01-01 00:00:00', '[]')"
            )

    assert migrate(blank_engine, migrations_through(tmp_path, 27)) == [27]

    assert rows(
        "SELECT external_id, is_default, avatar_url FROM social_account ORDER BY id"
    ) == [("a", 1, None), ("b", 1, None), ("c", 0, None)]
