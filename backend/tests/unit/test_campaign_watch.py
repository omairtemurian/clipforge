"""Tests for the campaign creator watch (SPEC-v2 3.18, campaign_watch): a
campaign's YouTube channels are registered in Auto Import, their new uploads
become projects with the campaign's preset, a fresh-upload mark and a higher
queue priority than other watched creators, and the watch stops when the
campaign closes or is deleted. respx answers with the recorded feeds."""

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
import respx
from campaign_api import PERMISSION_URL, PNG
from clipforge import auto_import, campaigns, jobs
from clipforge.campaign_watch import CampaignWatch, sync_channels
from clipforge.db import JobRow, ProjectRow
from clipforge.jobs import CAMPAIGN_PRIORITY, TOP_PRIORITY
from clipforge.models import (
    FRESH_UPLOAD_HOURS,
    Campaign,
    CampaignCreate,
    ProcessingSettings,
    Project,
    WatchedChannelCreate,
)
from clipforge.watch import youtube_handles
from clipforge.watch.youtube_watcher import AutoImporter
from fake_clock import FakeClock
from sqlalchemy import Engine
from sqlmodel import Session, select
from watch_fakes import NEWEST_PUBLISHED, PUSH_NEWEST, WallClock, hub_signature
from youtube_fakes import CHANNEL, feed_route

OTHER = "UCaaaaaaaaaaaaaaaaaaaaaa"
HANDLE_ID = "UCbbbbbbbbbbbbbbbbbbbbbb"
TODAY = date(2026, 10, 31)
LINE = "Clip of the Creator stream"


def channel_url(channel_id: str) -> str:
    return f"https://www.youtube.com/channel/{channel_id}"


def resolver(handle: str) -> str:
    """Looks up @creator only, as YouTube would."""
    if handle != "@creator":
        raise youtube_handles.HandleNotFound(f"YouTube has no channel {handle}")
    return HANDLE_ID


def make(engine: Engine, *urls: str, **fields: Any) -> Campaign:
    create = CampaignCreate.model_validate(
        {"name": "Creator", "source_channel_urls": list(urls)} | fields
    )
    return campaigns.create_campaign(engine, create)


def sync(engine: Engine, campaign: Campaign, today: date = TODAY) -> CampaignWatch:
    return sync_channels(engine, campaign, today, resolver)


def test_the_campaign_channels_are_registered_in_auto_import(engine: Engine) -> None:
    campaign = make(
        engine,
        channel_url(CHANNEL),
        "https://www.youtube.com/@creator",
        required_credit_line=LINE,
        caption_template="neon",
        min_duration_s=5,
        max_duration_s=25,
    )

    watch = sync(engine, campaign)

    assert watch.skipped == []
    watched = auto_import.list_channels(engine)
    assert [c.channel_id for c in watched] == [CHANNEL, HANDLE_ID]
    assert {c.campaign_id for c in watched} == {campaign.id}
    assert all(c.enabled for c in watched)
    assert watched[0].credit_line == LINE
    assert watched[0].settings.caption_template == "neon"
    assert watched[0].settings.length_presets == ["lt30"]
    assert auto_import.campaign_channels(engine, campaign.id) == watched


def test_links_that_cannot_be_watched_are_skipped_with_the_reason(
    engine: Engine,
) -> None:
    campaign = make(
        engine,
        "https://www.tiktok.com/@creator",
        "https://www.youtube.com/@nobody",
        channel_url(CHANNEL),
    )

    watch = sync(engine, campaign)

    assert [c.channel_id for c in watch.channels] == [CHANNEL]
    skipped = dict(watch.skipped)
    assert "not a YouTube channel link" in skipped["https://www.tiktok.com/@creator"]
    assert "no channel @nobody" in skipped["https://www.youtube.com/@nobody"]


def test_syncing_again_adds_nothing_and_drops_removed_links(engine: Engine) -> None:
    campaign = make(engine, channel_url(CHANNEL), channel_url(OTHER))
    sync(engine, campaign)
    sync(engine, campaign)
    assert len(auto_import.list_channels(engine)) == 2

    kept = campaigns.update_campaign(
        engine,
        campaign.id,
        campaigns.CampaignPatch(source_channel_urls=[channel_url(OTHER)]),
    )
    sync(engine, kept)

    assert [c.channel_id for c in auto_import.list_channels(engine)] == [OTHER]


def test_source_rights_need_the_complete_permission_evidence(engine: Engine) -> None:
    campaign = make(engine, channel_url(CHANNEL), permission_source_url=PERMISSION_URL)
    (without,) = sync(engine, campaign).channels
    auto_import.remove_channel(engine, without.id)

    proven = campaigns.set_permission_screenshot(engine, campaign.id, PNG, ".png")
    (with_proof,) = sync(engine, proven).channels

    assert without.source_rights is None
    assert with_proof.source_rights == "permission"


def test_the_channels_follow_the_campaign_status(engine: Engine) -> None:
    paused = make(engine, channel_url(CHANNEL), status="paused")
    ended = make(engine, channel_url(OTHER), end_date="2026-10-30")

    sync(engine, paused)
    sync(engine, ended)

    enabled = {c.channel_id: c.enabled for c in auto_import.list_channels(engine)}
    assert enabled == {CHANNEL: False, OTHER: False}

    reopened = campaigns.update_campaign(
        engine, paused.id, campaigns.CampaignPatch(status="active")
    )
    sync(engine, reopened)
    assert auto_import.find_channel(engine, CHANNEL).enabled is True  # type: ignore[union-attr]


def test_a_channel_the_owner_watches_is_adopted_unless_another_campaign_has_it(
    engine: Engine,
) -> None:
    mine = auto_import.add_channel(engine, WatchedChannelCreate(channel=CHANNEL))
    first = make(engine, channel_url(CHANNEL))
    second = make(engine, channel_url(CHANNEL), name="Second")

    assert sync(engine, first).channels[0].id == mine.id
    watch = sync(engine, second)

    assert watch.channels == []
    assert "watched for campaign" in watch.skipped[0][1]
    assert auto_import.get_channel(engine, mine.id).campaign_id == first.id


def test_deleting_a_campaign_stops_its_watch_only(engine: Engine) -> None:
    campaign = make(engine, channel_url(CHANNEL))
    sync(engine, campaign)
    own = auto_import.add_channel(engine, WatchedChannelCreate(channel=OTHER))

    campaigns.delete_campaign(engine, campaign.id)

    assert [c.id for c in auto_import.list_channels(engine)] == [own.id]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def importer(engine: Engine, clock: FakeClock) -> AutoImporter:
    wall = WallClock(clock, NEWEST_PUBLISHED - timedelta(seconds=20))
    return AutoImporter(
        engine, interval=60.0, clock=clock, rng=random.Random(3), wall_clock=wall
    )


def new_upload(imp: AutoImporter, clock: FakeClock, *ids: str) -> list[int]:
    """Read the feeds once (recording them), then again after the upload."""
    imp.tick()
    clock.now = max(imp.schedule.next_due(channel_id) for channel_id in ids)
    return imp.tick()


def project_row(engine: Engine, project_id: int) -> ProjectRow:
    with Session(engine) as session:
        row = session.get(ProjectRow, project_id)
        assert row is not None
        return row


def test_a_new_upload_becomes_a_campaign_project_with_its_preset(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeClock
) -> None:
    campaign = campaigns.set_permission_screenshot(
        engine,
        make(
            engine,
            channel_url(CHANNEL),
            permission_source_url=PERMISSION_URL,
            required_credit_line=LINE,
            caption_template="neon",
            min_duration_s=35,
            max_duration_s=80,
        ).id,
        PNG,
        ".png",
    )
    sync(engine, campaign)
    feed_route(respx_mock, "feed_before", "feed_after")

    (project_id,) = new_upload(importer(engine, clock), clock, CHANNEL)

    project = project_row(engine, project_id).to_model()
    assert project.campaign_id == campaign.id
    assert project.source_published_at is not None
    assert project.source_published_at.replace(tzinfo=UTC) == NEWEST_PUBLISHED
    assert project.credit_line == LINE
    assert project.source_rights == "permission"
    assert project.settings.caption_template == "neon"
    assert project.settings.length_presets == ["30_60", "60_90"]
    with Session(engine) as session:
        (job,) = session.exec(select(JobRow)).all()
    assert (job.project_id, job.priority) == (project_id, CAMPAIGN_PRIORITY)


def test_the_campaign_credit_line_wins_over_the_channel_default(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeClock
) -> None:
    campaign = make(engine, channel_url(CHANNEL), required_credit_line=LINE)
    sync(engine, campaign)
    (channel,) = auto_import.list_channels(engine)
    auto_import.set_channel_fields(engine, channel.id, credit_line="old line")
    feed_route(respx_mock, "feed_before", "feed_after")

    (project_id,) = new_upload(importer(engine, clock), clock, CHANNEL)

    assert project_row(engine, project_id).credit_line == LINE


def test_a_closed_campaign_imports_nothing(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeClock
) -> None:
    ended = make(engine, channel_url(CHANNEL), end_date="2026-10-30")
    sync(engine, ended, today=date(2026, 10, 29))  # still open then
    (channel,) = auto_import.list_channels(engine)
    assert channel.enabled
    route = feed_route(respx_mock, "feed_before", "feed_after")
    imp = importer(engine, clock)

    assert new_upload(imp, clock, CHANNEL) == []
    assert route.call_count == 0
    assert (
        imp.receive_push(CHANNEL, PUSH_NEWEST, hub_signature("x", PUSH_NEWEST)).status
        == 410
    )
    assert project_count(engine) == 0


def project_count(engine: Engine) -> int:
    with Session(engine) as session:
        return len(session.exec(select(ProjectRow)).all())


def test_a_campaign_upload_is_claimed_before_other_watched_uploads(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeClock
) -> None:
    plain = jobs.enqueue_process(engine, "https://youtu.be/plain", ProcessingSettings())
    auto_import.add_channel(engine, WatchedChannelCreate(channel=OTHER))
    sync(engine, make(engine, channel_url(CHANNEL)))
    feed_route(respx_mock, "feed_before", "feed_after")
    feed_route(respx_mock, "feed_before", "feed_after", channel=OTHER)

    project_ids = new_upload(importer(engine, clock), clock, CHANNEL, OTHER)

    assert len(project_ids) == 2
    order = [jobs.claim_next(engine) for _ in range(3)]
    claimed = [job.id for job in order if job is not None]
    with Session(engine) as session:
        priorities = {
            job.id: job.priority for job in session.exec(select(JobRow)).all()
        }
    assert [priorities[i] for i in claimed] == [CAMPAIGN_PRIORITY, TOP_PRIORITY, 0]
    assert claimed[-1] == plain
    assert CAMPAIGN_PRIORITY > TOP_PRIORITY


def test_an_ordinary_channel_keeps_its_project_without_a_campaign(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeClock
) -> None:
    auto_import.add_channel(engine, WatchedChannelCreate(channel=CHANNEL))
    feed_route(respx_mock, "feed_before", "feed_after")

    (project_id,) = new_upload(importer(engine, clock), clock, CHANNEL)

    project = project_row(engine, project_id).to_model()
    assert (project.campaign_id, project.source_published_at) == (None, None)
    assert project.fresh_upload is False


def project_of(**fields: Any) -> Project:
    return Project.model_validate(
        {
            "id": 1,
            "source_url": None,
            "source_path": "",
            "title": "",
            "duration": 1.0,
            "thumbnail_path": "",
            "settings": ProcessingSettings(),
            "status": "done",
            "created_at": datetime.now(UTC),
        }
        | fields
    )


@pytest.mark.parametrize(
    ("hours_ago", "campaign_id", "fresh"),
    [
        (1, 3, True),
        (FRESH_UPLOAD_HOURS - 1, 3, True),
        (FRESH_UPLOAD_HOURS + 1, 3, False),
        (1, None, False),
    ],
)
def test_the_fresh_badge_is_for_recent_campaign_uploads(
    hours_ago: int, campaign_id: int | None, fresh: bool
) -> None:
    published = datetime.now(UTC) - timedelta(hours=hours_ago)

    project = project_of(source_published_at=published, campaign_id=campaign_id)

    assert project.fresh_upload is fresh
    assert project.model_dump(mode="json")["fresh_upload"] is fresh


def test_a_project_without_a_publication_date_is_not_fresh() -> None:
    assert project_of(campaign_id=3).fresh_upload is False
