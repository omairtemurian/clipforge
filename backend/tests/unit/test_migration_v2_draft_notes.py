"""Tests for migration 037_v2_draft_notes: it adds the draft's notes column,
an empty list for the drafts that exist, and keeps their data."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.autopilot.rows import DraftRow
from clipforge.db import migrate
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, raw_campaign, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_drafts_get_no_notes(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 36))
    campaign_id = raw_campaign(blank_engine)
    clip_id = rows("SELECT id FROM clip")[0][0]
    with blank_engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO draft (clip_id, campaign_id, status, rule_results, "
            f"created_at) VALUES ({clip_id}, {campaign_id}, 'pending', '[]', "
            "'2030-01-01 00:00:00')"
        )
    drafts = rows("SELECT * FROM draft")

    assert migrate(blank_engine, migrations_through(tmp_path, 37)) == [37]

    after = rows("SELECT * FROM draft")
    assert [row[:-1] for row in after] == drafts
    assert [row[-1] for row in after] == ["[]"]
    migrate(blank_engine)
    with Session(blank_engine) as session:
        draft = session.get(DraftRow, after[0][0])
        assert draft is not None
        assert draft.to_model().notes == []
