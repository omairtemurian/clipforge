"""Tests for migration 026_v2_clip_enhance: every existing clip has speech
enhancement off, so it renders as before."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import ClipRow, migrate
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_clips_have_no_enhancement(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    ids = seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 25))
    clips = rows("SELECT * FROM clip ORDER BY id")

    assert migrate(blank_engine, migrations_through(tmp_path, 26)) == [26]

    assert rows("SELECT * FROM clip ORDER BY id") == [(*r, 0.0) for r in clips]
    names = [row[1] for row in rows("PRAGMA table_info(clip)")]
    assert names[-1] == "enhance"
    migrate(blank_engine)
    with Session(blank_engine) as session:
        assert [session.get_one(ClipRow, i).to_model().enhance for i in ids] == [
            0.0
        ] * len(ids)
