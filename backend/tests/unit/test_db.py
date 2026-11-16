"""Tests for migration 001 and the table rows it creates."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, TypeVar

import pytest
from clipforge.api_keys import ApiKeyRow
from clipforge.asset_rows import AssetRow, UsageRecordRow
from clipforge.autopilot.rows import (
    AutopilotPauseRow,
    AutopilotSettingsRow,
    DraftRow,
    FeedbackEventRow,
)
from clipforge.campaign_rows import CampaignRow
from clipforge.channel_rows import (
    WatchedChannelRow,
    WatchedStreamerRow,
    WatchedVideoRow,
    WatchEventRow,
)
from clipforge.clip_versions import ClipVersionRow
from clipforge.collection_rows import CollectionItemRow, CollectionRow
from clipforge.db import BrandTemplateRow, ClipRow, JobRow, ProjectRow, migrate
from clipforge.models import (
    Asset,
    BrandTemplate,
    Campaign,
    Clip,
    Draft,
    FeedbackEvent,
    Job,
    Post,
    ProcessingSettings,
    Project,
    Scores,
    SocialAccount,
    Submission,
    UsageRecord,
    WatchedChannel,
    WatchedStreamer,
    WatchedVideo,
    WatchEvent,
    Word,
)
from clipforge.notification_rows import NotificationRow
from clipforge.proedit.rows import (
    EdlItemRow,
    ProEditPlanRow,
    ProEditRunRow,
    StyleRecipeRow,
    StyleReferenceRow,
)
from clipforge.search.rows import SearchStateRow
from clipforge.social_rows import PostRow, SocialAccountRow
from clipforge.submission_rows import CampaignAccountRow, SubmissionRow
from clipforge.timeline import timeline_of
from clipforge.webhook_rows import WebhookDeliveryRow, WebhookRow
from sqlalchemy import Engine
from sqlalchemy.exc import StatementError
from sqlmodel import Session, SQLModel, inspect

Rows = Callable[[str], list[tuple[Any, ...]]]
RowT = TypeVar("RowT", bound=SQLModel)

ROW_MODELS = [
    (ProjectRow, Project),
    (ClipRow, Clip),
    (JobRow, Job),
    (BrandTemplateRow, BrandTemplate),
    (AssetRow, Asset),
    (UsageRecordRow, UsageRecord),
    (WatchedChannelRow, WatchedChannel),
    (WatchedVideoRow, WatchedVideo),
    (WatchedStreamerRow, WatchedStreamer),
    (WatchEventRow, WatchEvent),
    (CampaignRow, Campaign),
    (SocialAccountRow, SocialAccount),
    (PostRow, Post),
    (SubmissionRow, Submission),
    (DraftRow, Draft),
    (FeedbackEventRow, FeedbackEvent),
]
# Every table's row class; ApiKeyRow also stores the key's digest, which its
# model (ApiKey) never shows, WebhookRow the secret, and ClipVersionRow is
# a clip's history (current, clip_id), shown as ClipVersion; the collection
# rows are shown as Collection and CollectionItem; SearchStateRow is the
# search index's bookkeeping; NotificationRow also keeps a dedupe key;
# AutopilotPauseRow is the global pause switch; the Pro Edit rows are shown as
# StyleRecipe, StyleReference, ProEditPlan (with its EdlItemRows, numbered by
# item_id within the plan instead of an id) and ProEditRun.
ROWS: list[type[SQLModel]] = [row for row, _ in ROW_MODELS] + [
    ApiKeyRow,
    WebhookRow,
    WebhookDeliveryRow,
    ClipVersionRow,
    CollectionRow,
    CollectionItemRow,
    SearchStateRow,
    NotificationRow,
    CampaignAccountRow,
    AutopilotSettingsRow,
    AutopilotPauseRow,
    StyleRecipeRow,
    StyleReferenceRow,
    ProEditPlanRow,
    EdlItemRow,
    ProEditRunRow,
]
SCORES: dict[str, Any] = {
    "overall": 72,
    "hook": 80,
    "flow": 70,
    "value": 60,
    "trend": 50,
    "laugh": 0.85,
    "energy": 0.1,
}
PROJECT: dict[str, Any] = {
    "source_path": "in.mp4",
    "title": "Show",
    "duration": 120.0,
    "thumbnail_path": "thumb.jpg",
}
CLIP: dict[str, Any] = {
    "segments": [(1.0, 31.0)],
    "tracks": timeline_of([(1.0, 31.0)]),
    "title": "Bit",
    "hook_text": "Wait",
    "description": "A bit.",
    "hashtags": ["a", "b", "c"],
    "emphasis_words": [],
    "reason": "Laugh.",
    "scores": SCORES,
    "layout": "fill",
    "caption_template": "karaoke_bold",
}
JOB: dict[str, Any] = {"kind": "process", "step": "ingest", "log_path": "job.log"}


def _add(session: Session, row: RowT) -> RowT:
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _project(**fields: Any) -> ProjectRow:
    return ProjectRow(**PROJECT | {"settings": ProcessingSettings()} | fields)


def _clip(project_id: int | None, **fields: Any) -> ClipRow:
    return ClipRow(project_id=project_id, **CLIP | fields)


def _job(project_id: int | None, **fields: Any) -> JobRow:
    return JobRow(project_id=project_id, **JOB | fields)


def _sqlite_affinity(declared: str) -> str:
    """Return the column affinity SQLite derives from a declared type name."""
    declared = declared.upper()
    if "INT" in declared:
        return "INTEGER"
    if any(name in declared for name in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in declared or not declared:
        return "BLOB"
    if any(name in declared for name in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def test_runner_applies_migrations_once(blank_engine: Engine, rows: Rows) -> None:
    assert migrate(blank_engine) == list(range(1, 41))
    versions = rows("SELECT * FROM schema_version")
    assert [row[:2] for row in versions] == [
        (1, "init"),
        (2, "clip_style"),
        (3, "clip_framing"),
        (4, "v2_timeline"),
        (5, "v2_assets_rights"),
        (6, "v2_job_priority"),
        (7, "v2_job_attempts"),
        (8, "clip_auto_cut"),
        (9, "clip_auto_zoom"),
        (10, "clip_scene_reframes"),
        (11, "settings_panel"),
        (12, "inbox_import"),
        (13, "v2_channels"),
        (14, "v2_watch"),
        (15, "v2_campaigns"),
        (16, "v2_campaign_preset"),
        (17, "v2_campaign_watch"),
        (18, "v2_social"),
        (19, "v2_post_attempts"),
        (20, "v2_api_keys"),
        (21, "v2_webhooks"),
        (22, "v2_result_sets"),
        (23, "v2_clip_versions"),
        (24, "v2_clip_transitions"),
        (25, "v2_clip_hook"),
        (26, "v2_clip_enhance"),
        (27, "v2_account_default"),
        (28, "v2_always_hashtags"),
        (29, "v2_job_eta"),
        (30, "v2_collections"),
        (31, "v2_search"),
        (32, "v2_archive"),
        (33, "v2_notifications"),
        (34, "v2_submissions"),
        (35, "v2_autopilot"),
        (36, "v2_autopilot_pause"),
        (37, "v2_draft_notes"),
        (38, "v2_submission_answered_at"),
        (39, "proedit"),
        (40, "proedit_runs"),
    ]
    tables = {name for (name,) in rows("SELECT name FROM sqlite_master")}
    assert {
        "project",
        "clip",
        "job",
        "brand_template",
        "asset",
        "usage_record",
    } <= tables

    assert migrate(blank_engine) == []
    assert rows("SELECT * FROM schema_version") == versions


@pytest.mark.parametrize(("row", "model"), ROW_MODELS)
def test_rows_store_every_model_field(row: type[SQLModel], model: type[Any]) -> None:
    assert list(row.model_fields) == list(model.model_fields)
    assert [column.name for column in row.__table__.columns] == list(model.model_fields)


@pytest.mark.parametrize("row", ROWS)
def test_migrated_schema_matches_row_classes(
    engine: Engine, rows: Rows, row: Any
) -> None:
    table = row.__table__
    columns = inspect(engine).get_columns(table.name)
    assert [(c["name"], _sqlite_affinity(str(c["type"]))) for c in columns] == [
        (c.name, _sqlite_affinity(c.type.compile(engine.dialect)))
        for c in table.columns
    ]
    assert {c["name"] for c in columns if c["primary_key"]} == {
        c.name for c in table.primary_key
    }
    assert {c["name"]: c["nullable"] for c in columns if not c["primary_key"]} == {
        c.name: c.nullable for c in table.columns if not c.primary_key
    }
    foreign_keys = rows(
        'SELECT "from", "table", "to", on_delete '
        f"FROM pragma_foreign_key_list('{table.name}')"
    )
    assert set(foreign_keys) == {
        (fk.parent.name, fk.column.table.name, fk.column.name, fk.ondelete)
        for fk in table.foreign_keys
    }
    indexes = inspect(engine).get_indexes(table.name)
    assert {(i["name"], tuple(i["column_names"])) for i in indexes} == {
        (i.name, tuple(c.name for c in i.columns)) for i in table.indexes
    }


def test_project_round_trip_preserves_settings(engine: Engine, rows: Rows) -> None:
    settings = ProcessingSettings(
        genre="comedy",
        length_presets=["30_60"],
        timeframe_start=5.5,
        timeframe_end=300.25,
        num_clips=7,
        aspect="1:1",
        caption_template="neon",
        keyword_prompt="airport jokes",
        remove_fillers=True,
        brand_template_id=3,
    )
    fields: dict[str, Any] = {
        "source_url": "https://www.youtube.com/watch?v=abc",
        "source_path": "data/input/show.mp4",
        "title": "Live at the Apollo",
        "duration": 3601.75,
        "thumbnail_path": "data/work/1/thumb.jpg",
        "settings": settings,
        "status": "running",
        "created_at": datetime(
            2026, 10, 30, 22, 37, 5, 123456, timezone(timedelta(hours=1))
        ),
    }
    with Session(engine) as session:
        project_id = _add(session, ProjectRow(**fields)).id
    with Session(engine) as session:
        row = session.get(ProjectRow, project_id)
        assert row is not None
        loaded = row.to_model()

    assert loaded == Project(id=project_id, **fields)
    assert loaded.created_at.tzinfo == UTC
    (stored,) = rows("SELECT settings FROM project")
    assert json.loads(stored[0]) == settings.model_dump(mode="json")


def test_clip_round_trip_preserves_scores_and_cut_ranges(
    engine: Engine, rows: Rows
) -> None:
    fields: dict[str, Any] = {
        "scores": Scores(**SCORES),
        "cut_ranges": [(15.25, 16.5), (30.0, 31.125)],
        "caption_overrides": [
            Word(text="WHAT?!", start=20.1, end=20.6, speaker="S1", prob=0.93)
        ],
        "hashtags": ["comedy", "standup", "travel"],
        "emphasis_words": ["WHAT"],
        "layout": "split",
        "status": "rendered",
        "output_path": "data/output/1/1.mp4",
    }
    with Session(engine) as session:
        project_id = _add(session, _project()).id
        clip_id = _add(session, _clip(project_id, **fields)).id
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        assert isinstance(row.scores, Scores)
        assert row.cut_ranges == [(15.25, 16.5), (30.0, 31.125)]
        loaded = row.to_model()

    assert loaded == Clip(id=clip_id, project_id=project_id, **CLIP | fields)
    (stored,) = rows("SELECT scores, cut_ranges FROM clip")
    assert json.loads(stored[0]) == SCORES
    assert json.loads(stored[1]) == [[15.25, 16.5], [30.0, 31.125]]


def test_job_and_brand_template_round_trip(engine: Engine) -> None:
    brand: dict[str, Any] = {"name": "Main", "logo_path": "logo.png"}
    brand |= {"logo_position": "br", "logo_opacity": 0.8, "font": "Inter Bold"}
    brand |= {"primary_color": "#FF6B35", "intro_path": "intro.mp4", "outro_path": None}
    job: dict[str, Any] = {"kind": "render", "step": "render", "progress": 0.5}
    job |= {"status": "failed", "error": "ffmpeg exited 1", "log_path": "job.log"}
    job |= {"priority": -3, "attempts": 2}
    with Session(engine) as session:
        brand_id = _add(session, BrandTemplateRow(**brand)).id
        project_id = _add(session, _project()).id
        clip_id = _add(session, _clip(project_id)).id
        job_id = _add(session, _job(project_id, clip_id=clip_id, **job)).id
    with Session(engine) as session:
        brand_row = session.get(BrandTemplateRow, brand_id)
        job_row = session.get(JobRow, job_id)
        assert brand_row is not None and job_row is not None
        assert brand_row.to_model() == BrandTemplate(id=brand_id, **brand)
        assert job_row.to_model() == Job(
            id=job_id, project_id=project_id, clip_id=clip_id, **job
        )


def test_new_rows_start_in_their_initial_state(engine: Engine) -> None:
    with Session(engine) as session:
        project = _add(session, _project())
        clip = _add(session, _clip(project.id))
        job = _add(session, _job(project.id))

        assert (project.status, project.source_url) == ("queued", None)
        assert datetime.now(UTC) - project.created_at < timedelta(minutes=1)
        assert (clip.status, clip.output_path) == ("candidate", None)
        assert clip.cut_ranges == clip.caption_overrides == []
        assert (job.status, job.clip_id, job.error) == ("queued", None, None)
        assert job.progress == 0.0


def test_invalid_json_field_is_rejected_on_write(engine: Engine) -> None:
    with Session(engine) as session:
        project_id = _add(session, _project()).id
        session.add(_clip(project_id, scores=SCORES | {"overall": 150}))
        with pytest.raises(StatementError, match="less than or equal to 99"):
            session.commit()


def test_deleting_a_project_cascades_to_its_clips_and_jobs(
    engine: Engine, rows: Rows
) -> None:
    with Session(engine) as session:
        doomed, kept = _add(session, _project()), _add(session, _project())
        for project in (doomed, kept):
            clip = _add(session, _clip(project.id))
            session.add(_job(project.id))
            session.add(_job(project.id, clip_id=clip.id, kind="render"))
        session.commit()
        kept_id, kept_clip_id = kept.id, clip.id
        session.delete(doomed)
        session.commit()

    assert rows("SELECT id, project_id FROM clip") == [(kept_clip_id, kept_id)]
    jobs = rows("SELECT project_id, kind FROM job ORDER BY id")
    assert jobs == [(kept_id, "process"), (kept_id, "render")]

    with Session(engine) as session:
        session.delete(session.get(ClipRow, kept_clip_id))
        session.commit()
    assert rows("SELECT project_id, kind FROM job") == [(kept_id, "process")]


def test_ids_of_deleted_rows_are_not_reused(engine: Engine, rows: Rows) -> None:
    with Session(engine) as session:
        first = _add(session, _project())
        first_id = first.id
        session.delete(first)
        session.commit()
        assert _add(session, _project()).id == first_id + 1

    # autopilot_pause has one fixed row (id 1), no ids to hand out.
    tables = rows("SELECT name FROM sqlite_master WHERE sql LIKE '%AUTOINCREMENT%'")
    assert {name for (name,) in tables} == {
        row.__tablename__
        for row in ROWS
        if "id" in row.model_fields and row is not AutopilotPauseRow
    }
