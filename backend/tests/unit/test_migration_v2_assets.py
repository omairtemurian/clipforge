"""Tests for migration 005_v2_assets_rights: the asset and usage_record
tables, the project's rights fields, and the brand files of v1 registered as
assets."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clipforge.asset_rows import UsageRecordRow
from clipforge.db import ClipRow, ProjectRow, migrate
from clipforge.models import ProcessingSettings
from sqlalchemy import Engine
from sqlmodel import Session, col, select
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]

BRAND = (
    "INSERT INTO brand_template (name, logo_path, logo_position, logo_opacity,"
    " font, primary_color, intro_path, outro_path) VALUES (?, ?, 'tr', 0.8,"
    " 'Inter Bold', '#FFAA00', ?, ?)"
)


@pytest.fixture
def v1_engine(blank_engine: Engine, tmp_path: Path) -> Engine:
    """An engine for a database at the v1 schema (migrations 001 to 003)."""
    migrate_to_v1(blank_engine, tmp_path)
    return blank_engine


@pytest.fixture
def through_005(tmp_path: Path) -> Path:
    """A directory with the migrations up to 005 only."""
    return migrations_through(tmp_path, 5)


def add_brand_templates(engine: Engine) -> None:
    """Add a template with a logo, intro and outro, one with only a logo, and
    one whose logo was not saved yet (an empty path)."""
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute(BRAND, ("Full", "/data/brand/1/logo.png", "i.mp4", "o.mov"))
        cursor.execute(BRAND, ("Logo only", "/data/brand/2/logo.jpg", None, None))
        cursor.execute(BRAND, ("Pending", "", None, None))
        raw.commit()
    finally:
        raw.close()


def test_v1_brand_files_are_registered_as_assets(
    v1_engine: Engine, rows: Rows, through_005: Path
) -> None:
    add_brand_templates(v1_engine)

    assert migrate(v1_engine, through_005) == [4, 5]

    assert rows(
        "SELECT id, kind, path, license, attribution, source_url, tags FROM asset"
        " ORDER BY id"
    ) == [
        (1, "logo", "/data/brand/1/logo.png", "user-provided", "", None, '["brand"]'),
        (2, "logo", "/data/brand/2/logo.jpg", "user-provided", "", None, '["brand"]'),
        (3, "video", "i.mp4", "user-provided", "", None, '["brand","intro"]'),
        (4, "video", "o.mov", "user-provided", "", None, '["brand","outro"]'),
    ]


def test_v1_projects_migrate_with_rights_not_set(v1_engine: Engine) -> None:
    ids = seed_v1(v1_engine)

    migrate(v1_engine)

    with Session(v1_engine) as session:
        project = session.get_one(ProjectRow, 1).to_model()
        clips = [session.get_one(ClipRow, clip_id) for clip_id in ids]
    assert project.title == "Show"
    assert project.source_rights is None
    assert project.credit_line == ""
    assert project.campaign_id is None
    assert project.rights_set is False
    assert project.model_dump(mode="json")["rights_set"] is False
    assert len(clips) == len(ids)


def test_a_project_with_rights_is_flagged_as_set(engine: Engine) -> None:
    with Session(engine) as session:
        row = ProjectRow(
            source_path="in.mp4",
            title="Mine",
            duration=10.0,
            thumbnail_path="t.jpg",
            settings=ProcessingSettings(),
            source_rights="cc_by",
            credit_line="Video by Ada, CC BY 4.0",
            campaign_id=7,
        )
        session.add(row)
        session.commit()
        project = session.get_one(ProjectRow, row.id).to_model()

    assert (project.source_rights, project.rights_set) == ("cc_by", True)
    assert (project.credit_line, project.campaign_id) == ("Video by Ada, CC BY 4.0", 7)


def test_an_unknown_source_right_is_rejected(engine: Engine) -> None:
    with Session(engine) as session, pytest.raises(Exception, match="source_rights"):
        row = ProjectRow(
            source_path="in.mp4",
            title="Mine",
            duration=10.0,
            thumbnail_path="t.jpg",
            settings=ProcessingSettings(),
            source_rights="stolen",  # type: ignore[arg-type]
        )
        session.add(row)
        session.commit()
        session.get_one(ProjectRow, row.id).to_model()


def test_migration_runs_on_an_empty_database(
    v1_engine: Engine, rows: Rows, through_005: Path
) -> None:
    assert migrate(v1_engine, through_005) == [4, 5]

    assert rows("SELECT COUNT(*) FROM asset") == [(0,)]
    assert rows("SELECT COUNT(*) FROM usage_record") == [(0,)]
    names = [row[1] for row in rows("PRAGMA table_info(project)")]
    assert names[-3:] == ["source_rights", "credit_line", "campaign_id"]


def test_migration_is_applied_once(
    v1_engine: Engine, rows: Rows, through_005: Path
) -> None:
    add_brand_templates(v1_engine)
    assert migrate(v1_engine, through_005) == [4, 5]
    after = rows("SELECT * FROM asset ORDER BY id")

    assert migrate(v1_engine, through_005) == []

    assert rows("SELECT * FROM asset ORDER BY id") == after
    assert rows("SELECT version FROM schema_version WHERE version = 5") == [(5,)]


def test_fresh_database_gets_every_migration(
    blank_engine: Engine, through_005: Path
) -> None:
    assert migrate(blank_engine, through_005) == [1, 2, 3, 4, 5]
    assert migrate(blank_engine, through_005) == []


def test_usage_records_keep_their_data_when_the_project_is_deleted(
    engine: Engine, rows: Rows
) -> None:
    with Session(engine) as session:
        project = ProjectRow(
            source_path="in.mp4",
            title="Show",
            duration=10.0,
            thumbnail_path="t.jpg",
            settings=ProcessingSettings(),
        )
        session.add(project)
        session.flush()
        session.add(UsageRecordRow(project_id=project.id, kind="llm_tokens", units=900))
        session.add(UsageRecordRow(kind="whisper_seconds", units=61.5, cost_usd=0.0))
        session.commit()
        records = [
            row.to_model()
            for row in session.exec(
                select(UsageRecordRow).order_by(col(UsageRecordRow.id))
            )
        ]
        assert [(r.project_id, r.kind, r.units, r.cost_usd) for r in records] == [
            (project.id, "llm_tokens", 900, None),
            (None, "whisper_seconds", 61.5, 0.0),
        ]
        assert records[0].at.tzinfo is not None
        session.delete(project)
        session.commit()

    assert rows("SELECT project_id, kind, units FROM usage_record ORDER BY id") == [
        (None, "llm_tokens", 900.0),
        (None, "whisper_seconds", 61.5),
    ]
    assert rows("PRAGMA foreign_key_check") == []
