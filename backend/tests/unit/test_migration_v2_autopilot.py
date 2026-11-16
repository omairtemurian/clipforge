"""Tests for migration 035_v2_autopilot: it adds the empty autopilot_settings,
draft and feedback_event tables, whose columns are the rows', keeps the data
as it was, and a clip has one draft; the settings and drafts go with their
campaign and the feedback keeps what was learned when a clip is deleted."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clipforge.autopilot.rows import AutopilotSettingsRow, DraftRow, FeedbackEventRow
from clipforge.db import migrate
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from submission_fakes import new_campaign
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]
TABLES = {
    "autopilot_settings": AutopilotSettingsRow,
    "draft": DraftRow,
    "feedback_event": FeedbackEventRow,
}
# Columns that later migrations add (037_v2_draft_notes, 039_proedit).
LATER_COLUMNS = {
    "draft": {"notes"},
    "autopilot_settings": {
        "proedit_enabled",
        "proedit_preset",
        "proedit_max_intensity",
    },
}


def test_the_tables_are_added_empty(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 34))
    projects = rows("SELECT * FROM project")
    clips = rows("SELECT * FROM clip")

    assert migrate(blank_engine, migrations_through(tmp_path, 35)) == [35]

    assert rows("SELECT * FROM project") == projects
    assert rows("SELECT * FROM clip") == clips
    for table, row in TABLES.items():
        assert rows(f"SELECT * FROM {table}") == []
        names = [c[1] for c in rows(f"SELECT * FROM pragma_table_info('{table}')")]
        later = LATER_COLUMNS.get(table, set())
        assert names == [c.name for c in row.__table__.columns if c.name not in later]


def test_a_clip_has_one_draft_and_drafts_follow_their_campaign(
    engine: Engine, rows: Rows
) -> None:
    campaign = new_campaign(engine)
    clip_id = add_clip(engine, add_project(engine), "candidate", 70)
    draft = (
        "INSERT INTO draft (clip_id, campaign_id, status, rule_results, created_at) "
        f"VALUES ({clip_id}, {campaign.id}, 'pending', '[]', '2030-01-01 00:00:00')"
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(draft)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.exec_driver_sql(draft)

    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM campaign WHERE id = {campaign.id}")
    assert rows("SELECT * FROM draft") == []


def test_deleting_a_clip_removes_its_draft_but_not_its_feedback(
    engine: Engine, rows: Rows
) -> None:
    campaign = new_campaign(engine)
    clip_id = add_clip(engine, add_project(engine), "candidate", 70)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO draft (clip_id, campaign_id, status, rule_results, "
            f"created_at) VALUES ({clip_id}, {campaign.id}, 'pending', '[]', "
            "'2030-01-01 00:00:00')"
        )
        conn.exec_driver_sql(
            "INSERT INTO feedback_event (clip_id, campaign_id, action, at) "
            f"VALUES ({clip_id}, {campaign.id}, 'approved', '2030-01-01 00:00:00')"
        )

    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM clip WHERE id = {clip_id}")

    assert rows("SELECT * FROM draft") == []
    assert rows("SELECT clip_id, campaign_id FROM feedback_event") == [
        (None, campaign.id)
    ]
    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM campaign WHERE id = {campaign.id}")
    assert rows("SELECT * FROM feedback_event") == []
