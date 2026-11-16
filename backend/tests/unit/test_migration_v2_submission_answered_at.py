"""Tests for migration 038_v2_submission_answered_at: it adds the submission's
answered_at column, empty for the submissions that exist, and keeps their
data."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import migrate
from clipforge.submission_rows import SubmissionRow
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, raw_campaign, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_submissions_have_no_answer_time(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 37))
    campaign_id = raw_campaign(blank_engine)
    with blank_engine.begin() as conn:
        clip_id = conn.exec_driver_sql("SELECT id FROM clip LIMIT 1").scalar_one()
        conn.exec_driver_sql(
            "INSERT INTO social_account (platform, external_id, display_name, "
            "token_ref, scopes, connected_at, restrictions) VALUES ('youtube', "
            "'x', 'main', 'ref', '[]', '2030-01-01 00:00:00', '[]')"
        )
        conn.exec_driver_sql(
            "INSERT INTO post (clip_id, account_id, platform, payload, status, "
            f"attempts) VALUES ({clip_id}, 1, 'youtube', '{{}}', 'published', 1)"
        )
        post_id = conn.exec_driver_sql("SELECT id FROM post").scalar_one()
        conn.exec_driver_sql(
            "INSERT INTO submission (post_id, campaign_id, status, approved_views, "
            f"notes) VALUES ({post_id}, {campaign_id}, 'approved', 1000, 'ok')"
        )
    submissions = rows("SELECT * FROM submission")

    assert migrate(blank_engine, migrations_through(tmp_path, 38)) == [38]

    after = rows("SELECT * FROM submission")
    assert [row[:-1] for row in after] == submissions
    assert [row[-1] for row in after] == [None]
    migrate(blank_engine)
    with Session(blank_engine) as session:
        row = session.get(SubmissionRow, after[0][0])
        assert row is not None
        assert row.to_model().answered_at is None
