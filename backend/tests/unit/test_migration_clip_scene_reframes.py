"""Tests for migration 010_clip_scene_reframes: clips made before scenes
have none."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import ClipRow, migrate
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_clips_get_no_scene_reframes(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    ids = seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 9))
    before = rows("SELECT * FROM clip ORDER BY id")

    assert migrate(blank_engine, migrations_through(tmp_path, 10)) == [10]

    after = rows("SELECT * FROM clip ORDER BY id")
    assert after == [(*row, "[]") for row in before]
    names = [row[1] for row in rows("PRAGMA table_info(clip)")]
    assert names[-1] == "scene_reframes"
    # ClipRow needs the columns of the later migrations.
    migrate(blank_engine)
    with Session(blank_engine) as session:
        clips = [session.get_one(ClipRow, clip_id).to_model() for clip_id in ids]
    assert [c.scene_reframes for c in clips] == [[]] * len(ids)
