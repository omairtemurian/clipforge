"""Tests for migration 009_clip_auto_zoom: clips made before auto zoom have
none."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import ClipRow, migrate
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_clips_get_auto_zoom_off_and_no_keyframes(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    ids = seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 8))
    before = rows("SELECT * FROM clip ORDER BY id")

    assert migrate(blank_engine, migrations_through(tmp_path, 9)) == [9]

    after = rows("SELECT * FROM clip ORDER BY id")
    assert after == [(*row, 0, "[]") for row in before]
    names = [row[1] for row in rows("PRAGMA table_info(clip)")]
    assert names[-2:] == ["auto_zoom", "zoom_keyframes"]
    # ClipRow needs the columns of the later migrations.
    migrate(blank_engine)
    with Session(blank_engine) as session:
        clips = [session.get_one(ClipRow, clip_id).to_model() for clip_id in ids]
    assert [(c.auto_zoom, c.zoom_keyframes) for c in clips] == [(False, [])] * len(ids)
