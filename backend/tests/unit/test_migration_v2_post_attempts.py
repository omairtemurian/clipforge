"""Tests for migration 019_v2_post_attempts: it adds attempted_at and
next_attempt_at to the posts and keeps the posts and v1 data as they were."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import migrate
from sqlalchemy import Engine
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_post_attempt_times_are_added_empty_to_existing_posts(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 18))
    clip_id = rows("SELECT id FROM clip")[0][0]
    with blank_engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO social_account (platform, external_id, display_name, "
            "token_ref, scopes, connected_at, restrictions) VALUES ('tiktok', "
            "'a', 'A', 'ref-a', '[]', '2030-01-01 00:00:00', '[]')"
        )
        conn.exec_driver_sql(
            "INSERT INTO post (clip_id, account_id, platform, payload, "
            "scheduled_at, status, attempts) VALUES "
            f"({clip_id}, 1, 'tiktok', '{{}}', '2030-01-02 09:00:00', 'queued', 2)"
        )
    posts = rows("SELECT * FROM post")
    clips = rows("SELECT * FROM clip")

    assert migrate(blank_engine, migrations_through(tmp_path, 19)) == [19]

    assert rows("SELECT * FROM clip") == clips
    assert rows("SELECT * FROM post") == [(*posts[0], None, None)]
    columns = [row[1] for row in rows("SELECT * FROM pragma_table_info('post')")]
    assert columns[-2:] == ["attempted_at", "next_attempt_at"]
