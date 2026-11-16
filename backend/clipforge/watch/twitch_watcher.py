"""Twitch go-live alerts (T28c).

TwitchWatcher needs a Twitch app (TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET;
without them it makes no request and the Watchlist says "Needs Twitch app
keys"). It resolves each watched login to its broadcaster id (Get Users).
With a public callback URL it subscribes each broadcaster to the
stream.online EventSub webhook, which pushes the go-live
(handle_eventsub), and still asks Get Streams every 15 min as a safety
net; without one it asks Get Streams about every 60 s (jittered, backed
off after errors, one call for up to 100 streamers). A stream that went
live raises one alert (a watch_event keyed by the stream id, so a push and
a poll of the same stream make one). The live recorder (TASK-157) is not
built yet: go-live only alerts.
"""

import logging
import random
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine

from clipforge import config
from clipforge.models import DetectedVia, WatchedStreamer
from clipforge.poller import Poller
from clipforge.watch import twitch_eventsub as eventsub
from clipforge.watch.events import record_event
from clipforge.watch.rss_poll import FeedSchedule
from clipforge.watch.streamers import find_streamer, list_streamers
from clipforge.watch.streamers import set_streamer_fields as update
from clipforge.watch.times import WallClock, utc_now
from clipforge.watch.twitch_api import TwitchApp, TwitchError
from clipforge.watch.websub import needs_request

logger = logging.getLogger(__name__)

SAFETY_POLL_S = 900.0
TWITCH_URL = "https://www.twitch.tv/"


class TwitchWatcher(Poller):
    """Reports when the enabled watched streamers go live."""

    thread_name = "clipforge-twitch-watch"

    def __init__(
        self,
        engine: Engine,
        app: TwitchApp,
        *,
        interval: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
        wall_clock: WallClock = utc_now,
        public_url: str = "",
        data_dir: Path | None = None,
    ) -> None:
        super().__init__(interval=interval, clock=clock)
        self.engine = engine
        self.app = app
        self.wall_clock = wall_clock
        self.public_url = public_url
        self.data_dir = data_dir
        self.schedule = FeedSchedule(interval, clock=clock, rng=rng)

    @classmethod
    def from_settings(cls, engine: Engine) -> "TwitchWatcher":
        """Return the watcher of the configured Twitch app and interval."""
        settings = config.settings
        app = TwitchApp(settings.twitch_client_id, settings.twitch_client_secret)
        return cls(
            engine,
            app,
            interval=settings.auto_import_poll_s,
            public_url=settings.public_callback_url,
        )

    def tick(self) -> list[int]:
        """Check the streamers that are due and keep the push
        subscriptions; go-live queues no project, so return []."""
        if not self.app.configured:
            return []
        streamers = self._enabled()
        due = set(self.schedule.due(s.login for s in streamers))
        self._check([s for s in streamers if s.login in due])
        self._maintain_push(self._enabled())
        return []

    def poll(self) -> list[int]:
        """Check every enabled streamer once; return []."""
        if self.app.configured:
            self._check(self._enabled())
        return []

    def _enabled(self) -> list[WatchedStreamer]:
        return [s for s in list_streamers(self.engine) if s.enabled]

    def _check(self, streamers: list[WatchedStreamer]) -> None:
        streamers = self._resolve([s for s in streamers if s.user_id is None]) + [
            s for s in streamers if s.user_id is not None
        ]
        if not streamers:
            return
        try:
            live = self.app.live_streams([s.user_id or "" for s in streamers])
        except TwitchError as exc:
            self._failed(streamers, exc)
            return
        by_user = {str(stream.get("user_id")): stream for stream in live}
        for streamer in streamers:
            pushed = streamer.push_state == "subscribed"
            self.schedule.succeeded(
                streamer.login, interval=SAFETY_POLL_S if pushed else None
            )
            stream = by_user.get(streamer.user_id or "")
            update(
                self.engine,
                streamer.id,
                last_checked_at=self.wall_clock(),
                last_error=None,
            )
            if stream is None:
                if streamer.live_since is not None:
                    update(self.engine, streamer.id, live_since=None)
                continue
            self.went_live(streamer, stream, "poll")

    def _resolve(self, streamers: list[WatchedStreamer]) -> list[WatchedStreamer]:
        """Find the broadcaster ids of the streamers; return those found."""
        if not streamers:
            return []
        try:
            users = self.app.users([s.login for s in streamers])
        except TwitchError as exc:
            self._failed(streamers, exc)
            return []
        by_login = {str(user.get("login", "")).lower(): user for user in users}
        found = []
        for streamer in streamers:
            user = by_login.get(streamer.login)
            if user is None:
                self.schedule.succeeded(streamer.login)
                message = f"Twitch has no user named {streamer.login}"
                update(self.engine, streamer.id, last_error=message)
                continue
            name = str(user.get("display_name") or streamer.login)
            user_id = str(user["id"])
            update(self.engine, streamer.id, user_id=user_id, display_name=name)
            found.append(streamer.model_copy(update={"user_id": user_id}))
        return found

    def _failed(self, streamers: list[WatchedStreamer], exc: TwitchError) -> None:
        logger.warning("twitch watch: %s", exc)
        for streamer in streamers:
            self.schedule.failed(streamer.login)
            update(self.engine, streamer.id, last_error=str(exc))

    def went_live(
        self, streamer: WatchedStreamer, stream: Mapping[str, object], via: DetectedVia
    ) -> None:
        """Record that the streamer's stream (a Get Streams item or a
        stream.online event) is live; one alert per stream id."""
        started = eventsub.parse_time(stream.get("started_at"))
        name = stream.get("user_name") or stream.get("broadcaster_user_name")
        event = record_event(
            self.engine,
            platform="twitch",
            kind="live",
            external_id=str(stream.get("id", "")),
            source_name=str(name or streamer.display_name),
            title=str(stream.get("title", "")),
            url=TWITCH_URL + streamer.login,
            published_at=started,
            detected_at=self.wall_clock(),
            via=via,
        )
        live_since = started or self.wall_clock()
        if event is not None or streamer.live_since is None:
            update(
                self.engine, streamer.id, live_since=live_since, last_live_at=live_since
            )
        if event is not None:
            logger.info("twitch watch: %s went live (%s)", streamer.login, via)

    def _maintain_push(self, streamers: list[WatchedStreamer]) -> None:
        now = self.wall_clock()
        for streamer in streamers:
            if not self.public_url:
                if streamer.push_state != "off":
                    update(self.engine, streamer.id, push_state="off")
                continue
            if streamer.user_id is None or streamer.push_state == "subscribed":
                continue
            if not needs_request(
                streamer.push_state, streamer.push_requested_at, None, now
            ):
                continue
            self._subscribe(streamer, now)

    def _subscribe(self, streamer: WatchedStreamer, now: datetime) -> None:
        update(
            self.engine,
            streamer.id,
            push_state="pending",
            push_requested_at=now,
            push_error=None,
        )
        try:
            subscription_id = self.app.subscribe_online(
                streamer.user_id or "",
                eventsub.callback_url(self.public_url),
                eventsub.eventsub_secret(self.data_dir),
            )
        except TwitchError as exc:
            if exc.status == 409:  # Twitch already has this subscription
                update(self.engine, streamer.id, push_state="subscribed")
                return
            update(self.engine, streamer.id, push_state="failed", push_error=str(exc))
            return
        update(self.engine, streamer.id, subscription_id=subscription_id)

    def handle_eventsub(
        self, headers: Mapping[str, str], body: bytes
    ) -> eventsub.EventSubAnswer:
        """Answer an EventSub webhook message (see watch/twitch_eventsub)."""
        secret = eventsub.eventsub_secret(self.data_dir)
        message = eventsub.read_message(headers, body, secret, self.wall_clock())
        if message is None:
            logger.warning("twitch watch: refused an unsigned EventSub message")
            return eventsub.EventSubAnswer(403)
        subscription = message.subscription
        streamer = find_streamer(self.engine, message.broadcaster_id)
        if message.type == "webhook_callback_verification":
            challenge = str(message.payload.get("challenge", ""))
            ours = subscription.get("type") == "stream.online"
            if streamer is None or not streamer.enabled or not ours or not challenge:
                return eventsub.EventSubAnswer(404)
            update(
                self.engine,
                streamer.id,
                push_state="subscribed",
                subscription_id=str(subscription.get("id", "")) or None,
                push_error=None,
            )
            return eventsub.EventSubAnswer(200, challenge)
        if streamer is not None and message.type == "revocation":
            reason = str(subscription.get("status", "revoked"))
            update(
                self.engine,
                streamer.id,
                push_state="revoked",
                push_error=f"Twitch revoked the subscription: {reason}",
                subscription_id=None,
            )
        event = message.payload.get("event")
        online = subscription.get("type") == "stream.online"
        if streamer is not None and streamer.enabled and online:
            if message.type == "notification" and isinstance(event, dict):
                self.went_live(streamer, event, "push")
        return eventsub.EventSubAnswer(204)
