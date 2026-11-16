"""Tests for migration 034_v2_submissions: it adds the empty campaign_account
and submission tables, whose columns are the rows', keeps the data as it was,
a post has one submission, and deleting a post, a campaign or an account
removes or keeps the records as SPEC-v2 3.18 needs (a payout is never lost
with its campaign)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clipforge import submissions
from clipforge.db import migrate
from clipforge.submission_rows import CampaignAccountRow, SubmissionRow
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from submission_fakes import account, campaign_clip, new_campaign, publish
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def columns(rows: Rows, table: str) -> list[str]:
    return [row[1] for row in rows(f"SELECT * FROM pragma_table_info('{table}')")]


def test_the_tables_are_added_empty(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 33))
    projects = rows("SELECT * FROM project")
    clips = rows("SELECT * FROM clip")

    assert migrate(blank_engine, migrations_through(tmp_path, 34)) == [34]

    assert rows("SELECT * FROM project") == projects
    assert rows("SELECT * FROM clip") == clips
    assert rows("SELECT * FROM submission") == []
    assert rows("SELECT * FROM campaign_account") == []
    assert columns(rows, "submission") == [
        column.name
        for column in SubmissionRow.__table__.columns
        if column.name != "answered_at"  # added by migration 038
    ]
    assert columns(rows, "campaign_account") == [
        column.name for column in CampaignAccountRow.__table__.columns
    ]


def test_a_post_has_one_submission_and_follows_its_post_and_campaign(
    engine: Engine, rows: Rows
) -> None:
    campaign = new_campaign(engine)
    post_id = publish(engine, campaign_clip(engine, campaign.id), account(engine))
    (view,) = submissions.list_submissions(engine)
    duplicate = (
        "INSERT INTO submission (post_id, campaign_id, status, notes) "
        f"VALUES ({post_id}, {campaign.id}, 'not_submitted', '')"
    )
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.exec_driver_sql(duplicate)

    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM campaign WHERE id = {campaign.id}")
    assert rows(f"SELECT campaign_id FROM submission WHERE id = {view.id}") == [(None,)]

    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM post WHERE id = {post_id}")
    assert rows("SELECT * FROM submission") == []


def test_an_account_is_mapped_to_a_campaign_once_and_the_mapping_follows_both(
    engine: Engine, rows: Rows
) -> None:
    campaign, other = new_campaign(engine), new_campaign(engine, name="Other")
    youtube = account(engine)
    mapping = "INSERT INTO campaign_account (campaign_id, account_id) VALUES ({}, {})"
    with engine.begin() as conn:
        conn.exec_driver_sql(mapping.format(campaign.id, youtube))
        conn.exec_driver_sql(mapping.format(other.id, youtube))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.exec_driver_sql(mapping.format(campaign.id, youtube))

    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM campaign WHERE id = {campaign.id}")
    assert rows("SELECT campaign_id FROM campaign_account") == [(other.id,)]
    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM social_account WHERE id = {youtube}")
    assert rows("SELECT * FROM campaign_account") == []
