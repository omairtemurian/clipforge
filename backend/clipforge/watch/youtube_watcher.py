"""The watched YouTube channels' new videos become top-priority projects
(SPEC-v2 3.1, T28c).

AutoImporter learns of a new upload two ways. With a public callback URL
the WebSub hub pushes it (receive_push, called by the callback endpoint)
and the feed is still read every 15 min as a safety net; without one (or
until the hub verified the subscription) each feed is read about every
auto_import_poll_s (60 s) seconds, jittered, conditionally, backed off
after errors (watch/rss_poll). The first read that works for a channel only
records the videos already in its feed; from then on each video id not
recorded yet becomes a project queued at TOP_PRIORITY with the channel's
settings, rights and credit line, is recorded, and raises an alert (a
watch_event with when it was published and when it was detected). Pushes
and reads share one lock, so a video is imported exactly once. A push of an
entry published before the channel was added (YouTube also pushes title
and description changes) is recorded without a project. While a monthly
usage cap is used up nothing is imported. Each tick also expires the
autopilot's drafts that waited too long and sends the daily digest once its
time of day has come.
"""

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import campaign_watch, config, usage
from clipforge.auto_import import (
    find_channel,
    list_channels,
    record_video,
    seen_video_ids,
    set_channel_fields,
)
from clipforge.autopilot import digest, safety
from clipforge.autopilot.pipeline import import_settings
from clipforge.campaign_presets import preset_settings
from clipforge.db import JobRow
from clipforge.jobs import CAMPAIGN_PRIORITY, TOP_PRIORITY, enqueue_process
from clipforge.models import DetectedVia, WatchedChannel
from clipforge.poller import Poller
from clipforge.sources.youtube_feed import (
    FeedEntry,
    FeedError,
    fetch_feed,
    parse_feed,
)
from clipforge.watch import websub
from clipforge.watch.events import record_event
from clipforge.watch.rss_poll import FeedSchedule
from clipforge.watch.times import WallClock, as_utc, utc_now

logger = logging.getLogger(__name__)

SAFETY_POLL_S = 900.0


@dataclass(frozen=True)
class PushAnswer:
    """The callback's answer to a pushed notification: its HTTP status and
    the projects it queued."""

    status: int
    imported: tuple[int, ...] = ()


class AutoImporter(Poller):
    """Imports the new videos of the enabled watched channels as projects.

    tick() reads the due feeds and keeps the WebSub subscriptions; poll()
    reads every enabled feed at once. on_import is called after projects
    were queued (the app wakes the worker with it); transport replaces the
    network, clock / rng / wall_clock the time and jitter in tests.
    """

    thread_name = "clipforge-auto-import"

    def __init__(
        self,
        engine: Engine,
        *,
        interval: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        on_import: Callable[[], None] | None = None,
        transport: httpx.BaseTransport | None = None,
        rng: random.Random | None = None,
        wall_clock: WallClock = utc_now,
        public_url: str = "",
        data_dir: Path | None = None,
    ) -> None:
        super().__init__(interval=interval, clock=clock)
        self.engine = engine
        self.on_import = on_import
        self.transport = transport
        self.wall_clock = wall_clock
        self.public_url = public_url
        self.data_dir = data_dir
        self.schedule = FeedSchedule(interval, clock=clock, rng=rng)
        self._lock = threading.Lock()

    @classmethod
    def from_settings(
        cls, engine: Engine, on_import: Callable[[], None] | None = None
    ) -> "AutoImporter":
        """Return the importer with the configured poll interval and public
        callback URL."""
        return cls(
            engine,
            interval=config.settings.auto_import_poll_s,
            on_import=on_import,
            public_url=config.settings.public_callback_url,
        )

    def tick(self) -> list[int]:
        """Read the feeds that are due, renew the push subscriptions and
        expire the autopilot's old drafts (safety.expire_drafts) and send the
        day's digest when it is due (digest.send_due); return the ids of the
        queued projects."""
        channels = self._enabled_channels()
        due = set(self.schedule.due(c.channel_id for c in channels))
        imported = self._read([c for c in channels if c.channel_id in due])
        try:
            websub.maintain(
                self.engine,
                list_channels(self.engine),
                self.public_url,
                self.wall_clock(),
                transport=self.transport,
                data_dir=self.data_dir,
            )
        except Exception:
            logger.exception("auto import: renewing the push subscriptions failed")
        try:
            safety.expire_drafts(self.engine, self.wall_clock())
        except Exception:
            logger.exception("auto import: expiring the autopilot's drafts failed")
        try:
            digest.send_due(self.engine, self.wall_clock())
        except Exception:
            logger.exception("auto import: the daily digest failed")
        return imported

    def poll(self) -> list[int]:
        """Read the feed of every enabled channel once; return the ids of the
        queued projects."""
        return self._read(self._enabled_channels())

    def _read(self, channels: list[WatchedChannel]) -> list[int]:
        imported: list[int] = []
        try:
            for channel in channels:
                imported += self.check_channel(channel)
        except usage.UsageCapExceeded as exc:
            logger.warning("auto import: not importing new videos yet: %s", exc)
        if imported and self.on_import is not None:
            self.on_import()
        return imported

    def check_channel(self, channel: WatchedChannel) -> list[int]:
        """Read one channel's feed and queue a project for each new video;
        return their ids. Raises UsageCapExceeded (nothing more is queued)."""
        key = channel.channel_id
        try:
            result = fetch_feed(key, self.transport, self.schedule.validators(key))
        except FeedError as exc:
            logger.warning("auto import: %s: %s", key, exc)
            self.schedule.failed(key)
            set_channel_fields(self.engine, channel.id, last_error=str(exc))
            return []
        interval = self._poll_interval(channel)
        self.schedule.succeeded(key, interval=interval)
        feed = result.feed
        imported: list[int] = []
        complete = False
        try:
            if feed is not None:
                imported, complete = self._import_entries(
                    channel, feed.entries, "poll", channel.last_checked_at is None
                )
            else:
                complete = True
        finally:
            if complete:
                self.schedule.succeeded(key, result.validators, interval)
            title = feed.title if feed is not None and feed.title else channel.title
            set_channel_fields(
                self.engine,
                channel.id,
                title=title,
                last_checked_at=self.wall_clock(),
                last_error=None,
            )
        return imported

    def receive_push(
        self, channel_id: str, body: bytes, signature: str | None
    ) -> PushAnswer:
        """Handle a notification the hub pushed for a channel: 410 if it is
        not watched (the hub drops the subscription), 403 if the signature
        is missing or wrong, 400 if it is not a feed, else 204 after
        importing its new videos."""
        channel = find_channel(self.engine, channel_id)
        if channel is None or not self._watched(channel):
            return PushAnswer(410)
        secret = websub.topic_secret(channel_id, self.data_dir)
        if not websub.valid_signature(body, signature, secret):
            logger.warning("auto import: refused an unsigned push for %s", channel_id)
            return PushAnswer(403)
        try:
            feed = parse_feed(body)
        except FeedError:
            return PushAnswer(400)
        try:
            imported, _ = self._import_entries(channel, feed.entries, "push", False)
        except usage.UsageCapExceeded as exc:
            logger.warning("auto import: not importing pushed videos yet: %s", exc)
            return PushAnswer(204)
        if imported and self.on_import is not None:
            self.on_import()
        return PushAnswer(204, tuple(imported))

    def _poll_interval(self, channel: WatchedChannel) -> float | None:
        """The slower safety interval of a channel the hub pushes, else
        None (the schedule's)."""
        lease = channel.push_lease_expires_at
        pushed = channel.push_state == "subscribed" and lease is not None
        if pushed and lease is not None and as_utc(lease) > self.wall_clock():
            return max(self.interval, SAFETY_POLL_S)
        return None

    def _import_entries(
        self,
        channel: WatchedChannel,
        entries: list[FeedEntry],
        via: DetectedVia,
        first_read: bool,
    ) -> tuple[list[int], bool]:
        """Import the entries not seen yet, oldest first; return the project
        ids and whether every entry was recorded."""
        imported: list[int] = []
        complete = True
        added = as_utc(channel.created_at)
        with self._lock:
            seen = seen_video_ids(self.engine, channel.id)
            for entry in reversed(entries):
                if entry.video_id in seen:
                    continue
                seen.add(entry.video_id)
                older = entry.published is not None and as_utc(entry.published) < added
                if first_read or (via == "push" and older):
                    record_video(self.engine, channel.id, entry, None)
                    continue
                try:
                    imported.append(self._import(channel, entry, via))
                except usage.UsageCapExceeded:
                    raise
                except Exception:
                    complete = False
                    logger.exception("auto import: importing %s failed", entry.url)
        return imported, complete

    def _enabled_channels(self) -> list[WatchedChannel]:
        return [c for c in list_channels(self.engine) if self._watched(c)]

    def _watched(self, channel: WatchedChannel) -> bool:
        """Whether the channel's videos are imported now (enabled, and its
        campaign, if any, still open)."""
        today = self.wall_clock().date()
        return campaign_watch.is_watched(self.engine, channel, today)

    def _import(
        self, channel: WatchedChannel, entry: FeedEntry, via: DetectedVia
    ) -> int:
        """Queue a top-priority project for the video with the channel's
        defaults, record the video and its alert; return the project id. A
        campaign channel's project gets the campaign (preset settings,
        CAMPAIGN_PRIORITY and the date the video was published, for its
        fresh badge) and, with the campaign's autopilot on, the autopilot's
        settings (autopilot.pipeline.import_settings)."""
        usage.check_caps(self.engine)
        campaign = campaign_watch.load_campaign(self.engine, channel)
        settings = channel.settings
        rights = channel.source_rights
        credit_line = channel.credit_line
        if campaign is not None:
            settings = preset_settings(settings, campaign)
            settings = import_settings(self.engine, campaign, settings)
            rights = rights or campaign_watch.channel_rights(campaign)
            credit_line = campaign.required_credit_line.strip() or credit_line
        job_id = enqueue_process(
            self.engine,
            entry.url,
            settings,
            source_rights=rights,
            credit_line=credit_line,
            priority=TOP_PRIORITY if campaign is None else CAMPAIGN_PRIORITY,
            campaign_id=None if campaign is None else campaign.id,
            source_published_at=entry.published if campaign is not None else None,
        )
        with Session(self.engine) as session:
            job = session.get(JobRow, job_id)
            assert job is not None
            project_id = job.project_id
        record_video(self.engine, channel.id, entry, project_id)
        record_event(
            self.engine,
            platform="youtube",
            kind="upload",
            external_id=entry.video_id,
            source_name=channel.title or channel.channel_id,
            title=entry.title,
            url=entry.url,
            project_id=project_id,
            published_at=entry.published,
            detected_at=self.wall_clock(),
            via=via,
        )
        logger.info(
            "auto import: %s (%s) is project %d (%s)",
            entry.video_id,
            channel.channel_id,
            project_id,
            via,
        )
        return project_id
