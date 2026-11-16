"""A database at the v1 schema (migrations 001 to 003) with v1 clips, to
test migrating v1 data (tests only)."""

import json
import shutil
from pathlib import Path

from clipforge.db import MIGRATIONS_DIR, migrate
from sqlalchemy import Engine

V1_VERSIONS = (1, 2, 3)
# v1 spans, one of them with doubles that need all 17 digits to round-trip.
V1_SPANS = [(10.0, 12.5), (0.1 + 0.2, 31.259999999999998), (100.125, 160.0)]
V1_PROJECT = (
    "INSERT INTO project (source_path, title, duration, thumbnail_path, settings,"
    " status, created_at) VALUES ('in.mp4', 'Show', 300.0, 't.jpg', '{}', 'done',"
    " '2026-10-31 10:00:00')"
)
V1_CLIP = (
    'INSERT INTO clip (project_id, start, "end", title, hook_text, description,'
    " hashtags, emphasis_words, reason, scores, layout, caption_template,"
    " caption_overrides, cut_ranges, status, output_path, caption_style,"
    " crop_offset, framing) VALUES (?, ?, ?, ?, 'Wait', 'A bit.',"
    " '[\"a\",\"b\",\"c\"]', '[]', 'Laugh.', ?, 'split', 'neon', '[]', ?,"
    " 'rendered', 'out.mp4', '{\"size\":80}', 0.25, '{\"tracker\":false}')"
)
SCORES = {"overall": 72, "hook": 80, "flow": 70, "value": 60, "trend": 50}
SCORES |= {"laugh": 0.85, "energy": 0.1}


def migrations_through(tmp_path: Path, last: int) -> Path:
    """Return a directory in tmp_path with a copy of the migrations up to
    version last."""
    directory = tmp_path / f"migrations_through_{last}"
    directory.mkdir()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if int(path.name[:3]) <= last:
            shutil.copy(path, directory / path.name)
    return directory


def migrate_through(engine: Engine, tmp_path: Path, last: int) -> None:
    """Apply only the migrations up to version last to the empty database of
    engine."""
    applied = migrate(engine, migrations_through(tmp_path, last))
    assert applied == list(range(1, last + 1))


def migrate_to_v1(engine: Engine, tmp_path: Path) -> None:
    """Apply only the v1 migrations to the empty database of engine."""
    migrate_through(engine, tmp_path, V1_VERSIONS[-1])


def seed_v1(engine: Engine) -> list[int]:
    """Add a v1 project with a clip for each of V1_SPANS (the second with cut
    ranges) and a render job of the first; delete a fourth clip, so the
    clip table's AUTOINCREMENT counter is past the last id. Returns the
    clips' ids."""
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute(V1_PROJECT)
        project_id = cursor.lastrowid
        ids = []
        for index, (start, end) in enumerate([*V1_SPANS, (1.0, 2.0)]):
            cuts = json.dumps([[start + 1, start + 2]] if index == 1 else [])
            values = (project_id, start, end, f"Bit {index}", json.dumps(SCORES))
            cursor.execute(V1_CLIP, (*values, cuts))
            ids.append(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO job (project_id, clip_id, kind, step, progress, status,"
            " log_path) VALUES (?, ?, 'render', 'render', 1.0, 'done', 'job.log')",
            (project_id, ids[0]),
        )
        cursor.execute("DELETE FROM clip WHERE id = ?", (ids[-1],))
        raw.commit()
    finally:
        raw.close()
    return [clip_id for clip_id in ids[:-1] if clip_id is not None]


def raw_campaign(engine: Engine) -> int:
    """Add a campaign by raw SQL with the columns of migration 038 or before,
    so a test can add one at an old schema; its id."""
    with engine.begin() as conn:
        cursor = conn.exec_driver_sql(
            "INSERT INTO campaign (name, creator_name, source_channel_urls, "
            "platform_board, badge, budget_note, allowed_platforms, "
            "required_hashtags, required_credit_line, required_tags_mentions, "
            "banned_content_notes, submission_instructions, status, notes) "
            "VALUES ('Pizza', '', '[]', 'other', 'open', '', '[]', '[]', '', '[]', "
            "'', '', 'active', '')"
        )
        return int(cursor.lastrowid)
