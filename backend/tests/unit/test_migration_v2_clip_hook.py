"""Tests for migration 025_v2_clip_hook: every existing clip has no hook,
so it renders as before (its v1 hook_text still drawn)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import ClipRow, migrate
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_clips_have_no_hook(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    ids = seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 24))
    clips = rows("SELECT * FROM clip ORDER BY id")

    assert migrate(blank_engine, migrations_through(tmp_path, 25)) == [25]

    assert rows("SELECT * FROM clip ORDER BY id") == [(*r, None) for r in clips]
    names = [row[1] for row in rows("PRAGMA table_info(clip)")]
    assert names[-1] == "hook"
    migrate(blank_engine)
    with Session(blank_engine) as session:
        assert [session.get_one(ClipRow, i).to_model().hook for i in ids] == [
            None
        ] * len(ids)
