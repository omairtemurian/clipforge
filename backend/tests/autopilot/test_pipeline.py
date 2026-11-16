"""Tests of the autopilot draft pipeline (clipforge.autopilot.pipeline,
SPEC-v2 3.19): a new upload of a watched campaign creator becomes a project
made the autopilot's way, and when its job is done its best clips become
drafts (pending, or needs_fix with the failed rules), never more than
max_clips_per_source. The autopilot never posts, schedules or submits.
Fake clocks; respx answers with the recorded feeds."""

import inspect
from datetime import UTC, datetime

import pytest
import respx
from autopilot_fakes import (
    CREDIT,
    add_rendered,
    finish_job,
    import_upload,
    project_job,
    turn_on,
    watched_campaign,
)
from campaign_api import in_campaign
from clipforge.autopilot import pipeline
from clipforge.autopilot.rows import DraftRow
from clipforge.db import JobRow, ProjectRow
from clipforge.models import AutopilotSettings, Draft, ProcessingSettings
from clipforge.social_rows import PostRow
from clipforge.submission_rows import SubmissionRow
from fake_clock import FakeWallClock
from seed import add_clip
from social_fakes import clip_of, set_rights
from sqlalchemy import Engine
from sqlmodel import Session, col, select
from submission_fakes import account

NOW = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeWallClock:
    """The autopilot's clock, at NOW."""
    wall = FakeWallClock(NOW)
    monkeypatch.setattr(pipeline, "utc_now", wall)
    return wall


def drafts(engine: Engine) -> list[Draft]:
    with Session(engine) as session:
        rows = session.exec(select(DraftRow).order_by(col(DraftRow.id))).all()
        return [row.to_model() for row in rows]


def project_settings(engine: Engine, project_id: int) -> ProcessingSettings:
    with Session(engine) as session:
        row = session.get(ProjectRow, project_id)
        assert row is not None
        return row.to_model().settings


def failed(draft: Draft) -> list[str]:
    return [r.rule for r in draft.rule_results if not r.passed]


def test_a_new_upload_is_made_the_autopilot_way(
    engine: Engine, respx_mock: respx.MockRouter
) -> None:
    campaign = watched_campaign(engine)
    turn_on(
        engine,
        campaign.id,
        max_clips_per_source=2,
        min_clip_s=20,
        caption_template="neon_lime",
    )

    project_id = import_upload(engine, respx_mock)

    made = project_settings(engine, project_id)
    assert made.num_clips == 2
    assert made.length_presets == ["custom"]
    assert (made.custom_length_min_s, made.custom_length_max_s) == (20, 60)
    assert made.caption_template == "neon_lime"


def test_with_the_autopilot_off_a_new_upload_keeps_the_campaign_preset(
    engine: Engine, respx_mock: respx.MockRouter
) -> None:
    campaign = watched_campaign(engine, caption_template="neon")
    turn_on(engine, campaign.id, enabled=False, max_clips_per_source=1)

    made = project_settings(engine, import_upload(engine, respx_mock))

    assert made.num_clips == ProcessingSettings().num_clips
    assert made.caption_template == "neon"
    assert made.length_presets == ["lt30", "30_60"]


def test_a_new_upload_yields_at_most_max_clips_drafts_failing_ones_need_a_fix(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeWallClock
) -> None:
    campaign = watched_campaign(engine, caption_template="neon")
    turn_on(engine, campaign.id, max_clips_per_source=3, caption_template="neon_lime")
    project_id = import_upload(engine, respx_mock)
    worst = add_rendered(engine, project_id, 40)
    too_long = add_rendered(engine, project_id, 95, start=0.0, end=75.0)
    best = add_rendered(engine, project_id, 90)
    second = add_rendered(engine, project_id, 70)
    clock.advance(minutes=20)

    finish_job(engine, project_id)

    made = drafts(engine)
    assert [d.clip_id for d in made] == [too_long, best, second]
    assert worst not in {d.clip_id for d in made}
    assert {d.campaign_id for d in made} == {campaign.id}
    assert [d.status for d in made] == ["needs_fix", "pending", "pending"]
    assert failed(made[0]) == ["max_duration"]
    assert "over 60s" in made[0].rule_results[4].detail
    assert all(failed(d) == [] for d in made[1:])
    assert len(made[1].rule_results) == 9
    assert {d.created_at for d in made} == {clock.now}
    assert all(d.decided_at is None and d.reject_reason is None for d in made)
    passing = clip_of(engine, best)
    assert passing.caption_template == "neon_lime"
    assert CREDIT in passing.description
    with Session(engine) as session:
        job = session.get(JobRow, project_job(engine, project_id))
        assert job is not None and job.status == "done"


def test_a_clip_that_breaks_several_rules_lists_each(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeWallClock
) -> None:
    campaign = watched_campaign(engine)
    turn_on(engine, campaign.id)
    project_id = import_upload(engine, respx_mock)
    set_rights(engine, project_id, None)
    add_clip(engine, project_id, "rendered", 80, start=0.0, end=2.0)

    (draft,) = pipeline.make_drafts(engine, project_id, clock.now)

    assert draft.status == "needs_fix"
    assert failed(draft) == ["source_rights", "min_duration", "credit_line", "mentions"]


def test_making_drafts_again_adds_none_past_the_cap(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeWallClock
) -> None:
    campaign = watched_campaign(engine)
    turn_on(engine, campaign.id, max_clips_per_source=2)
    project_id = import_upload(engine, respx_mock)
    first = add_rendered(engine, project_id, 60)
    assert [d.clip_id for d in pipeline.make_drafts(engine, project_id)] == [first]

    better = add_rendered(engine, project_id, 90)
    add_rendered(engine, project_id, 80)
    again = pipeline.make_drafts(engine, project_id, clock.advance(hours=1))

    assert [d.clip_id for d in again] == [better]
    assert pipeline.make_drafts(engine, project_id) == []
    assert len(drafts(engine)) == 2


def test_only_rendered_clips_become_drafts(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeWallClock
) -> None:
    campaign = watched_campaign(engine)
    turn_on(engine, campaign.id)
    project_id = import_upload(engine, respx_mock)
    add_clip(engine, project_id, "failed", 99)
    add_clip(engine, project_id, "candidate", 98)
    rendered = add_rendered(engine, project_id, 50)

    made = pipeline.make_drafts(engine, project_id, clock.now)

    assert [d.clip_id for d in made] == [rendered]


def test_no_drafts_with_the_autopilot_off(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeWallClock
) -> None:
    watched_campaign(engine)
    project_id = import_upload(engine, respx_mock)
    add_rendered(engine, project_id, 80)

    finish_job(engine, project_id)

    assert drafts(engine) == []


def test_a_project_the_owner_put_in_the_campaign_gets_no_drafts(
    engine: Engine, clock: FakeWallClock
) -> None:
    campaign = watched_campaign(engine)
    turn_on(engine, campaign.id)
    project_id = in_campaign(engine, campaign.id)
    add_rendered(engine, project_id, 80)

    assert pipeline.make_drafts(engine, project_id, clock.now) == []
    assert pipeline.make_drafts(engine, 999, clock.now) == []


def test_a_failure_to_make_drafts_leaves_the_job_done(
    engine: Engine,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    campaign = watched_campaign(engine)
    turn_on(engine, campaign.id)
    project_id = import_upload(engine, respx_mock)
    add_rendered(engine, project_id, 80)

    def broken(engine: Engine, project_id: int) -> list[Draft]:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(pipeline, "make_drafts", broken)
    finish_job(engine, project_id)

    with Session(engine) as session:
        job = session.get(JobRow, project_job(engine, project_id))
        assert job is not None and job.status == "done"
    assert f"no drafts for project {project_id}" in caplog.text


@pytest.mark.parametrize(
    ("low", "high", "presets", "custom"),
    [
        (None, None, ["lt30", "30_60"], (None, None)),
        (None, 45.0, ["custom"], (5.0, 45.0)),
        (10.0, 30.0, ["custom"], (10.0, 30.0)),
        (70.0, None, ["lt30", "30_60"], (None, None)),
    ],
)
def test_the_autopilot_length_range_fills_in_the_campaign_bounds(
    engine: Engine,
    low: float | None,
    high: float | None,
    presets: list[str],
    custom: tuple[float | None, float | None],
) -> None:
    campaign = watched_campaign(engine)
    preset = ProcessingSettings(length_presets=["lt30", "30_60"], num_clips=8)
    autopilot = AutopilotSettings(
        campaign_id=campaign.id, enabled=True, min_clip_s=low, max_clip_s=high
    )

    made = pipeline.autopilot_processing(preset, autopilot, campaign)

    assert made.length_presets == presets
    assert (made.custom_length_min_s, made.custom_length_max_s) == custom
    assert made.num_clips == 3


def test_a_caption_template_deleted_since_is_not_used(engine: Engine) -> None:
    campaign = watched_campaign(engine)
    autopilot = AutopilotSettings(
        campaign_id=campaign.id, enabled=True, caption_template="gone"
    )

    made = pipeline.autopilot_processing(ProcessingSettings(), autopilot, campaign)

    assert made.caption_template == ProcessingSettings().caption_template


def test_the_autopilot_never_posts_schedules_or_submits(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeWallClock
) -> None:
    campaign = watched_campaign(engine)
    youtube = account(engine, "youtube")
    turn_on(
        engine,
        campaign.id,
        account_ids=[youtube],
        slots={"timezone": "Europe/Zurich", "times": ["09:00", "18:00"]},
    )
    project_id = import_upload(engine, respx_mock)
    for overall in (90, 80, 70):
        add_rendered(engine, project_id, overall)

    finish_job(engine, project_id)
    pipeline.make_drafts(engine, project_id, clock.advance(days=1))

    assert [d.status for d in drafts(engine)] == ["pending"] * 3
    with Session(engine) as session:
        assert session.exec(select(PostRow)).all() == []
        assert session.exec(select(SubmissionRow)).all() == []
    source = inspect.getsource(pipeline)
    for module in ("posts", "post_schedule", "scheduler", "submissions", "publishers"):
        assert f"clipforge.{module}" not in source
        assert f"import {module}" not in source
