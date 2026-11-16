"""Helpers of the autopilot tests (tests only): a campaign whose creator's
channel is watched, its autopilot turned on, a new upload that Auto Import
turns into a project (respx answers with the recorded feeds) and the
project's process job finishing with given clips."""

import random
from datetime import timedelta
from pathlib import Path
from typing import Any

import respx
from builders import source_meta
from campaign_api import PERMISSION_URL, PNG
from clipforge import campaigns, process
from clipforge.autopilot import settings
from clipforge.campaign_presets import preset_new_clips
from clipforge.campaign_watch import sync_channels
from clipforge.db import ClipRow, JobRow
from clipforge.models import (
    AutopilotSettings,
    AutopilotSettingsUpdate,
    Campaign,
    CampaignCreate,
    ScoredList,
)
from clipforge.pipeline.step import (
    META,
    SNAPPED,
    STEP_NAMES,
    job_dir,
    mark_done,
    write_json,
)
from clipforge.process_clips import CLIPS_STAGE, REFRAME_STEP
from clipforge.watch.youtube_watcher import AutoImporter
from fake_clock import FakeClock
from seed import add_clip
from social_fakes import write_video
from sqlalchemy import Engine
from sqlmodel import Session, select
from watch_fakes import NEWEST_PUBLISHED, WallClock
from youtube_fakes import CHANNEL, feed_route

CREDIT = "Clip of Chef Mario"


def watched_campaign(engine: Engine, **fields: Any) -> Campaign:
    """Add an active campaign with complete permission evidence that allows
    YouTube, asks for a credit line, hashtags, a mention and 5-60 s clips,
    and watch its creator's channel (CHANNEL) in Auto Import."""
    data: dict[str, Any] = {
        "name": "Pizza Clips",
        "source_channel_urls": [f"https://www.youtube.com/channel/{CHANNEL}"],
        "permission_source_url": PERMISSION_URL,
        "allowed_platforms": ["youtube"],
        "required_credit_line": CREDIT,
        "required_hashtags": ["pizza"],
        "required_tags_mentions": ["@chefmario"],
        "min_duration_s": 5,
        "max_duration_s": 60,
        "rate_per_1k_usd": 1.5,
    } | fields
    created = campaigns.create_campaign(engine, CampaignCreate.model_validate(data))
    campaign = campaigns.set_permission_screenshot(engine, created.id, PNG, ".png")
    sync_channels(engine, campaign, NEWEST_PUBLISHED.date(), lambda h: h)
    return campaign


def turn_on(engine: Engine, campaign_id: int, **fields: Any) -> AutopilotSettings:
    """Save the campaign's autopilot settings: on, with fields."""
    update = AutopilotSettingsUpdate.model_validate({"enabled": True} | fields)
    return settings.save_settings(engine, campaign_id, update)


def import_upload(engine: Engine, respx_mock: respx.MockRouter) -> int:
    """Let Auto Import read the channel's feed, then find the new upload;
    the id of the project it made."""
    feed_route(respx_mock, "feed_before", "feed_after")
    clock = FakeClock()
    importer = AutoImporter(
        engine,
        interval=60.0,
        clock=clock,
        rng=random.Random(3),
        wall_clock=WallClock(clock, NEWEST_PUBLISHED - timedelta(seconds=20)),
    )
    importer.tick()
    clock.now = importer.schedule.next_due(CHANNEL)
    (project_id,) = importer.tick()
    return project_id


def project_job(engine: Engine, project_id: int) -> int:
    """The id of the project's process job."""
    with Session(engine) as session:
        job_id = session.exec(
            select(JobRow.id).where(JobRow.project_id == project_id)
        ).one()
    assert job_id is not None
    return job_id


def add_rendered(engine: Engine, project_id: int, overall: int, **changes: Any) -> int:
    """Add a rendered clip of 10-25 s (its video on disk) as the process job
    saves it, with the project's caption template and campaign text; its
    id. changes replace its fields (start/end: its span)."""
    span = {"start": 10.0, "end": 25.0}
    clip_id = add_clip(
        engine, project_id, "rendered", overall, f"Clip {overall}", **span | changes
    )
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None and row.output_path is not None
        write_video(Path(row.output_path))
    preset_new_clips(engine, project_id, [clip_id])
    return clip_id


def finish_job(engine: Engine, project_id: int) -> None:
    """Run the project's process job to the end with every step and clip
    stage finished before (the clips are those the test added), as a job
    that resumes after its last stage does."""
    job_id = project_job(engine, project_id)
    work = job_dir(job_id)
    work.mkdir(parents=True)
    write_json(work / META, source_meta())
    write_json(work / SNAPPED, ScoredList(clips=[]))
    for name in (*STEP_NAMES, CLIPS_STAGE, REFRAME_STEP):
        mark_done(work, name)
    process.run_process_job(engine, job_id)
