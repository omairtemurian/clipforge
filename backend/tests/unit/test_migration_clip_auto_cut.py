"""Tests for migration 008_clip_auto_cut: clips made before auto cut have
none."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import ClipRow, migrate
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_clips_get_auto_cut_off(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    ids = seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 7))
    before = rows("SELECT * FROM clip ORDER BY id")

    assert migrate(blank_engine, migrations_through(tmp_path, 8)) == [8]

    assert rows("SELECT * FROM clip ORDER BY id") == [(*row, 0) for row in before]
    names = [row[1] for row in rows("PRAGMA table_info(clip)")]
    assert names[-1] == "auto_cut"
    migrate(blank_engine)
    with Session(blank_engine) as session:
        clips = [session.get_one(ClipRow, clip_id).to_model() for clip_id in ids]
    assert [clip.auto_cut for clip in clips] == [False] * len(ids)
