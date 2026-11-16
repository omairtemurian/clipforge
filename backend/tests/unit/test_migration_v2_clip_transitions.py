"""Tests for migration 024_v2_clip_transitions: every existing clip has no
transitions, so it renders as before."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import ClipRow, migrate
from clipforge.models import ClipTransitions
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_clips_have_no_transitions(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    ids = seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 23))
    clips = rows("SELECT * FROM clip ORDER BY id")

    assert migrate(blank_engine, migrations_through(tmp_path, 24)) == [24]

    empty = '{"auto": null, "sections": []}'
    assert rows("SELECT * FROM clip ORDER BY id") == [(*r, empty) for r in clips]
    migrate(blank_engine)
    with Session(blank_engine) as session:
        assert [session.get_one(ClipRow, i).to_model().transitions for i in ids] == [
            ClipTransitions()
        ] * len(ids)
