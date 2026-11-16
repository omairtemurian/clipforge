"""Tests for migration 011_settings_panel: clips made before have auto color
off and captions on; a project's length_preset becomes length_presets."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipforge.db import ClipRow, migrate
from sqlalchemy import Engine
from sqlmodel import Session
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]


def test_existing_clips_and_projects_get_the_new_settings(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    migrate_to_v1(blank_engine, tmp_path)
    ids = seed_v1(blank_engine)
    migrate(blank_engine, migrations_through(tmp_path, 10))
    old = {"genre": "comedy", "length_preset": "60_90", "num_clips": 4}
    raw = blank_engine.raw_connection()
    try:
        raw.cursor().execute("UPDATE project SET settings = ?", (json.dumps(old),))
        raw.commit()
    finally:
        raw.close()
    before = rows("SELECT * FROM clip ORDER BY id")

    assert migrate(blank_engine, migrations_through(tmp_path, 11)) == [11]

    after = rows("SELECT * FROM clip ORDER BY id")
    assert after == [(*row, 0, 1) for row in before]
    [(settings,)] = rows("SELECT settings FROM project")
    assert json.loads(settings) == {
        "genre": "comedy",
        "length_presets": ["60_90"],
        "num_clips": 4,
    }
    # ClipRow needs the columns of the later migrations.
    migrate(blank_engine)
    with Session(blank_engine) as session:
        clips = [session.get_one(ClipRow, clip_id).to_model() for clip_id in ids]
    assert [(c.auto_color, c.show_captions) for c in clips] == [(False, True)] * 3
