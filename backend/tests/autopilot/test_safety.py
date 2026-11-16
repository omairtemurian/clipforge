"""Tests of the autopilot's safety switches (clipforge.autopilot.safety,
SPEC-v2 3.19): no drafts while every autopilot is paused, the permission
evidence is missing, the campaign is paused or ended, its end date passed or
the day's quota is reached (each an alert, once a day); 3 failed uploads in a
row turn the autopilot off with an alert (draft expiry: test_draft_expiry).
Fake clocks; respx answers with the recorded feeds."""

from datetime import UTC, datetime, timedelta

import pytest
import respx
from autopilot_fakes import (
    add_rendered,
    finish_job,
    import_upload,
    turn_on,
    watched_campaign,
)
from campaign_api import in_campaign
from clipforge import campaigns, process
from clipforge.autopilot import pipeline, safety
from clipforge.autopilot.rows import DraftRow
from clipforge.autopilot.settings import get_settings
from clipforge.channel_rows import WatchedChannelRow, WatchedVideoRow
from clipforge.db import ProjectRow
from clipforge.models import CampaignPatch, DraftStatus, ProcessingSettings
from clipforge.notification_rows import NotificationRow
from fake_clock import FakeWallClock
from seed import add_project
from sqlalchemy import Engine
from sqlmodel import Session, col, select
from submission_fakes import new_campaign

NOW = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeWallClock:
    """The autopilot's clock, at NOW."""
    wall = FakeWallClock(NOW)
    monkeypatch.setattr(pipeline, "utc_now", wall)
    return wall


def alerts(engine: Engine) -> list[str]:
    """The titles of the autopilot_stopped notifications, oldest first."""
    with Session(engine) as session:
        return list(
            session.exec(
                select(NotificationRow.title)
                .where(NotificationRow.kind == "autopilot_stopped")
                .order_by(col(NotificationRow.id))
            )
        )


def draft_statuses(engine: Engine) -> list[DraftStatus]:
    with Session(engine) as session:
        return list(session.exec(select(DraftRow.status).order_by(col(DraftRow.id))))


def num_clips(engine: Engine, project_id: int) -> int:
    with Session(engine) as session:
        row = session.get(ProjectRow, project_id)
        assert row is not None
        return row.to_model().settings.num_clips


def upload_with_clips(
    engine: Engine, respx_mock: respx.MockRouter, clips: int = 2
) -> int:
    """Import the new upload of a watched campaign whose autopilot is on
    (1 clip per source) and give it passing rendered clips; the project id."""
    project_id = import_upload(engine, respx_mock)
    for overall in range(clips):
        add_rendered(engine, project_id, 90 - overall)
    return project_id


def stop_the_campaign(engine: Engine, campaign_id: int, **fields: object) -> None:
    campaigns.update_campaign(engine, campaign_id, CampaignPatch.model_validate(fields))


@pytest.mark.parametrize(
    ("fields", "reason", "detail"),
    [
        (
            {"permission_source_url": None},
            "permission_missing",
            "add the permission source URL, the date the permission was checked",
        ),
        ({"status": "paused"}, "campaign_inactive", "the campaign is paused"),
        ({"status": "ended"}, "campaign_inactive", "the campaign is ended"),
        (
            {"end_date": "2026-10-30"},
            "campaign_ended",
            "the campaign ended on 2026-10-30",
        ),
    ],
)
def test_the_campaign_stops_its_autopilot_with_one_alert_a_day(
    engine: Engine,
    respx_mock: respx.MockRouter,
    clock: FakeWallClock,
    fields: dict[str, object],
    reason: str,
    detail: str,
) -> None:
    campaign = watched_campaign(engine)
    turn_on(engine, campaign.id, max_clips_per_source=1)
    project_id = upload_with_clips(engine, respx_mock)
    stop_the_campaign(engine, campaign.id, **fields)

    assert pipeline.make_drafts(engine, project_id, NOW) == []
    assert draft_statuses(engine) == []
    stop = safety.status(engine, NOW).stops
    assert [(s.campaign_id, s.reason, s.detail) for s in stop] == [
        (campaign.id, reason, detail)
    ]
    assert alerts(engine) == ["Autopilot of Pizza Clips stopped"]
    stopped = campaigns.get_campaign(engine, campaign.id)
    assert pipeline.import_settings(engine, stopped, ProcessingSettings()) == (
        ProcessingSettings()
    )
    assert len(alerts(engine)) == 1
    assert pipeline.make_drafts(engine, project_id, NOW + timedelta(days=1)) == []
    assert len(alerts(engine)) == 2


def test_an_upload_while_permission_is_missing_is_a_plain_campaign_project(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeWallClock
) -> None:
    campaign = watched_campaign(engine)
    turn_on(engine, campaign.id, max_clips_per_source=1)
    stop_the_campaign(engine, campaign.id, permission_source_url=None)

    project_id = upload_with_clips(engine, respx_mock)

    assert num_clips(engine, project_id) == ProcessingSettings().num_clips
    assert pipeline.make_drafts(engine, project_id, NOW) == []
    assert alerts(engine) == ["Autopilot of Pizza Clips stopped"]


def test_the_campaign_ending_today_still_makes_drafts(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeWallClock
) -> None:
    campaign = watched_campaign(engine, end_date=NOW.astimezone().date())
    turn_on(engine, campaign.id, max_clips_per_source=1)
    project_id = upload_with_clips(engine, respx_mock)

    assert num_clips(engine, project_id) == 1
    assert len(pipeline.make_drafts(engine, project_id, NOW)) == 1
    assert safety.status(engine, NOW).stops == []
    assert alerts(engine) == []


def test_the_global_pause_halts_every_autopilot_without_an_alert(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeWallClock
) -> None:
    campaign = watched_campaign(engine)
    other = new_campaign(engine)
    turn_on(engine, campaign.id, max_clips_per_source=1)
    turn_on(engine, other.id)
    assert safety.set_paused(engine, True, NOW) == NOW
    assert safety.set_paused(engine, True, NOW + timedelta(hours=1)) == NOW

    project_id = upload_with_clips(engine, respx_mock)

    assert num_clips(engine, project_id) == ProcessingSettings().num_clips
    assert pipeline.make_drafts(engine, project_id, NOW) == []
    status = safety.status(engine, NOW)
    assert (status.paused, status.paused_at) == (True, NOW)
    assert [(s.campaign_id, s.reason) for s in status.stops] == [
        (campaign.id, "paused"),
        (other.id, "paused"),
    ]
    assert alerts(engine) == []

    assert safety.set_paused(engine, False) is None
    assert len(pipeline.make_drafts(engine, project_id, NOW)) == 1
    assert [(s.campaign_id, s.reason) for s in safety.status(engine, NOW).stops] == [
        (other.id, "permission_missing")
    ]


def test_the_daily_quota_caps_the_drafts_that_may_be_posted(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeWallClock
) -> None:
    campaign = watched_campaign(engine)
    turn_on(engine, campaign.id, max_clips_per_source=3, max_posts_per_day=2)
    project_id = upload_with_clips(engine, respx_mock, clips=3)

    assert num_clips(engine, project_id) == 3
    assert len(pipeline.make_drafts(engine, project_id, NOW)) == 2
    assert pipeline.make_drafts(engine, project_id, NOW + timedelta(hours=2)) == []
    (stop,) = safety.status(engine, NOW).stops
    assert stop.reason == "daily_quota"
    assert alerts(engine) == ["Autopilot of Pizza Clips stopped"]

    tomorrow = NOW + timedelta(days=1)
    assert safety.status(engine, tomorrow).stops == []
    assert len(pipeline.make_drafts(engine, project_id, tomorrow)) == 1
    assert draft_statuses(engine) == ["pending", "pending", "pending"]


def test_drafts_that_need_a_fix_do_not_count_against_the_quota(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeWallClock
) -> None:
    campaign = watched_campaign(engine)
    turn_on(engine, campaign.id, max_clips_per_source=3, max_posts_per_day=1)
    project_id = import_upload(engine, respx_mock)
    add_rendered(engine, project_id, 95, start=0.0, end=75.0)
    add_rendered(engine, project_id, 90)
    add_rendered(engine, project_id, 80)

    pipeline.make_drafts(engine, project_id, NOW)

    assert draft_statuses(engine) == ["needs_fix", "pending"]
    assert safety.drafts_today(engine, campaign.id, NOW.astimezone().date()) == 1


def old_upload(engine: Engine, campaign_id: int, status: str, video: str) -> int:
    """An earlier upload of the campaign's watched channel that Auto Import
    made, its processing status; the project id."""
    project_id = in_campaign(engine, campaign_id)
    with Session(engine) as session:
        channel_id = session.exec(select(WatchedChannelRow.id)).one()
        assert channel_id is not None
        session.add(
            WatchedVideoRow(
                watched_channel_id=channel_id, video_id=video, project_id=project_id
            )
        )
        row = session.get(ProjectRow, project_id)
        assert row is not None
        row.status = status  # type: ignore[assignment]
        session.add(row)
        session.commit()
    return project_id


def test_three_failed_uploads_in_a_row_turn_the_autopilot_off(
    engine: Engine,
    respx_mock: respx.MockRouter,
    clock: FakeWallClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = watched_campaign(engine)
    turn_on(engine, campaign.id)
    old_upload(engine, campaign.id, "failed", "a")
    old_upload(engine, campaign.id, "done", "b")
    second = old_upload(engine, campaign.id, "failed", "c")
    assert safety.after_failed_job(engine, second) is False
    in_campaign(engine, campaign.id)  # not an upload: does not count
    assert get_settings(engine, campaign.id).enabled
    project_id = import_upload(engine, respx_mock)
    old_upload(engine, campaign.id, "failed", "d")

    def broken(*args: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(process, "make_clips", broken)

    with pytest.raises(RuntimeError, match="disk full"):
        finish_job(engine, project_id)

    assert not get_settings(engine, campaign.id).enabled
    assert alerts(engine) == ["Autopilot of Pizza Clips turned off"]
    assert safety.status(engine, NOW).stops == []
    assert safety.after_failed_job(engine, project_id) is False


def test_failures_of_a_campaign_without_autopilot_change_nothing(
    engine: Engine,
) -> None:
    campaign = watched_campaign(engine)
    ids = [old_upload(engine, campaign.id, "failed", v) for v in "abc"]

    assert safety.after_failed_job(engine, ids[-1]) is False
    assert safety.after_failed_job(engine, add_project(engine)) is False
    assert safety.after_failed_job(engine, 999) is False
    assert alerts(engine) == []
