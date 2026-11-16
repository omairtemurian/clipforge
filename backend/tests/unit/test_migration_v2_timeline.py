"""Tests for migration 004_v2_timeline: v1 clips' start and end become
segments and a video track, on empty and populated databases."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clipforge.db import ClipRow, migrate
from clipforge.models import Clip
from clipforge.timeline import timeline_of
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import (
    SCORES,
    V1_SPANS,
    V1_VERSIONS,
    migrate_to_v1,
    migrations_through,
    seed_v1,
)

Rows = Callable[[str], list[tuple[Any, ...]]]

EMPTY_TRACKS = ("broll", "overlays", "text", "music", "sfx", "voiceover")


@pytest.fixture
def through_004(tmp_path: Path) -> Path:
    """The migrations up to 004_v2_timeline."""
    return migrations_through(tmp_path, 4)


@pytest.fixture
def v1_engine(blank_engine: Engine, tmp_path: Path) -> Engine:
    """An engine for a database at the v1 schema (migrations 001 to 003)."""
    migrate_to_v1(blank_engine, tmp_path)
    return blank_engine


def test_v1_clips_migrate_to_one_segment_and_a_video_track(
    v1_engine: Engine, rows: Rows, through_004: Path
) -> None:
    ids = seed_v1(v1_engine)

    assert migrate(v1_engine, through_004) == [4]

    stored = rows("SELECT id, segments, tracks FROM clip ORDER BY id")
    assert [row[0] for row in stored] == ids
    for (_, segments, tracks), (start, end) in zip(stored, V1_SPANS, strict=True):
        assert json.loads(segments) == [[start, end]]
        video = {"id": "video-0", "kind": "source", "asset_id": None}
        video |= {"start": start, "end": end, "props": {}}
        assert json.loads(tracks) == {"video": [video]} | {
            name: [] for name in EMPTY_TRACKS
        }
    # ClipRow needs the columns of the later migrations.
    migrate(v1_engine)
    with Session(v1_engine) as session:
        clips = [session.get(ClipRow, clip_id) for clip_id in ids]
        models = [row.to_model() for row in clips if row is not None]
    for clip, (start, end) in zip(models, V1_SPANS, strict=True):
        assert clip.segments == [(start, end)]
        assert (clip.start, clip.end) == (start, end)
        assert clip.tracks == timeline_of([(start, end)])
    assert models[1].cut_ranges == [(V1_SPANS[1][0] + 1, V1_SPANS[1][0] + 2)]


def test_migration_keeps_the_other_clip_fields_and_jobs(
    v1_engine: Engine, rows: Rows, through_004: Path
) -> None:
    ids = seed_v1(v1_engine)
    columns = (
        "id, project_id, title, hook_text, description, hashtags, emphasis_words,"
        " reason, scores, layout, caption_template, caption_overrides, cut_ranges,"
        " status, output_path, caption_style, crop_offset, framing"
    )
    before = rows(f"SELECT {columns} FROM clip ORDER BY id")

    migrate(v1_engine, through_004)

    assert rows(f"SELECT {columns} FROM clip ORDER BY id") == before
    assert rows("SELECT clip_id FROM job") == [(ids[0],)]
    assert rows("PRAGMA foreign_key_check") == []
    migrate(v1_engine)
    with Session(v1_engine) as session:
        clip = session.get(ClipRow, ids[0])
        assert clip is not None
        session.delete(clip)
        session.commit()
    assert rows("SELECT clip_id FROM job") == []


def test_migrated_table_does_not_reuse_deleted_clip_ids(
    v1_engine: Engine, through_004: Path
) -> None:
    ids = seed_v1(v1_engine)
    migrate(v1_engine, through_004)
    migrate(v1_engine)
    clip = Clip.model_validate(
        {"id": 0, "project_id": 1, "segments": [(3.0, 9.0)]}
        | {"tracks": timeline_of([(3.0, 9.0)]), "title": "New", "hook_text": ""}
        | {"description": "", "hashtags": [], "emphasis_words": [], "reason": ""}
        | {"scores": SCORES, "layout": "fill", "caption_template": "neon"}
        | {"caption_overrides": [], "cut_ranges": [], "status": "candidate"}
        | {"output_path": None}
    )
    fields = {name: getattr(clip, name) for name in Clip.model_fields if name != "id"}
    with Session(v1_engine) as session:
        row = ClipRow(**fields)
        session.add(row)
        session.commit()
        assert row.id == ids[-1] + 2


def test_migration_runs_on_an_empty_database(
    v1_engine: Engine, rows: Rows, through_004: Path
) -> None:
    assert migrate(v1_engine, through_004) == [4]

    assert rows("SELECT COUNT(*) FROM clip") == [(0,)]
    names = [row[1] for row in rows("PRAGMA table_info(clip)")]
    assert names[:4] == ["id", "project_id", "segments", "tracks"]
    assert "start" not in names and "end" not in names
    assert rows("PRAGMA index_list(clip)")[0][1] == "ix_clip_project_id"


def test_migration_is_applied_once(
    v1_engine: Engine, rows: Rows, through_004: Path
) -> None:
    seed_v1(v1_engine)
    assert migrate(v1_engine, through_004) == [4]
    after = rows("SELECT * FROM clip ORDER BY id")

    assert migrate(v1_engine, through_004) == []

    assert rows("SELECT * FROM clip ORDER BY id") == after
    assert rows("SELECT version FROM schema_version WHERE version = 4") == [(4,)]


def test_fresh_database_gets_every_migration(
    blank_engine: Engine, through_004: Path
) -> None:
    assert migrate(blank_engine, through_004) == [*V1_VERSIONS, 4]
    assert migrate(blank_engine, through_004) == []
