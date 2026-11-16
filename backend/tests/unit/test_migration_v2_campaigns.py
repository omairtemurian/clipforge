"""Tests for migration 015_v2_campaigns: the campaign table starts empty, v1
data is kept, and a campaign row keeps the lists and the permission
evidence."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clipforge.db import migrate
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]
CAMPAIGN = (
    "INSERT INTO campaign (name, creator_name, source_channel_urls, platform_board,"
    " badge, budget_note, allowed_platforms, required_hashtags,"
    " required_credit_line, required_tags_mentions, banned_content_notes,"
    " submission_instructions, status, notes) VALUES ('Clips', '', '[]', 'other',"
    " 'open', '', '[]', '[]', '', '[]', '', '', 'active', '')"
)


def test_v1_data_is_kept_and_the_table_starts_empty(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 14))
    before = [rows(f"SELECT * FROM {t}") for t in ("project", "clip", "job")]

    assert migrate(blank_engine, migrations_through(tmp_path, 15)) == [15]

    assert [rows(f"SELECT * FROM {t}") for t in ("project", "clip", "job")] == before
    assert rows("SELECT COUNT(*) FROM campaign") == [(0,)]


def test_the_optional_fields_default_to_null(engine: Engine, rows: Rows) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(CAMPAIGN)

    assert rows(
        "SELECT campaign_url, permission_source_url, permission_screenshot_asset_id,"
        " permission_checked_at, rate_per_1k_usd, min_duration_s, max_duration_s,"
        " monetization_allowed_elsewhere, end_date FROM campaign"
    ) == [(None,) * 9]


def test_a_screenshot_asset_must_exist(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(CAMPAIGN)
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql(
                "UPDATE campaign SET permission_screenshot_asset_id = 99"
            )
