"""Fakes of the creator watch tests (tests only): a wall clock tied to the
fake monotonic clock, the recorded Twitch answers and push bodies, and
the signatures that YouTube's hub and Twitch would send.

fixtures/twitch/*.json are the example answers of the Twitch API reference
and EventSub docs (dev.twitch.tv, read 2026-10-31) for one broadcaster,
afro (id 101051819), whose live stream 40952121085 the Get Streams example
shows; fixtures/youtube_feed/push_newest.xml is the WebSub notification of
the YouTube push guide for the newest video of feed_after.xml.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from clipforge.watch import twitch_eventsub
from fake_clock import FakeClock

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TWITCH = FIXTURES / "twitch"
PUSH_NEWEST = (FIXTURES / "youtube_feed" / "push_newest.xml").read_bytes()
# When the newest video of feed_after.xml was published.
NEWEST_PUBLISHED = datetime(2026, 10, 31, 14, 0, 33, tzinfo=UTC)
PUBLIC_URL = "https://watch.example.com"
LOGIN, USER_ID, STREAM_ID = "afro", "101051819", "40952121085"


class WallClock:
    """A wall clock that moves with a FakeClock: start at clock time 1000."""

    def __init__(self, clock: FakeClock, start: datetime) -> None:
        self.clock = clock
        self.start = start

    def __call__(self) -> datetime:
        return self.start + timedelta(seconds=self.clock.now - 1000.0)


def twitch_json(name: str) -> dict[str, Any]:
    """The recorded Twitch payload fixtures/twitch/<name>.json."""
    payload: dict[str, Any] = json.loads((TWITCH / f"{name}.json").read_text())
    return payload


def twitch_response(name: str, status: int = 200) -> httpx.Response:
    """The recorded Twitch answer fixtures/twitch/<name>.json."""
    return httpx.Response(status, json=twitch_json(name))


def hub_signature(secret: str, body: bytes, method: str = "sha1") -> str:
    """The X-Hub-Signature that a WebSub hub sends with body."""
    digest = hmac.new(secret.encode(), body, getattr(hashlib, method)).hexdigest()
    return f"{method}={digest}"


def eventsub_headers(
    secret: str,
    body: bytes,
    message_type: str,
    sent: datetime,
    message_id: str = "e76c6bd4-55c9-4987-8304-da1588d8988b",
) -> dict[str, str]:
    """The headers Twitch sends with an EventSub webhook message."""
    timestamp = sent.isoformat().replace("+00:00", "Z")
    return {
        "Twitch-Eventsub-Message-Id": message_id,
        "Twitch-Eventsub-Message-Retry": "0",
        "Twitch-Eventsub-Message-Type": message_type,
        "Twitch-Eventsub-Message-Signature": twitch_eventsub.signature(
            secret, message_id, timestamp, body
        ),
        "Twitch-Eventsub-Message-Timestamp": timestamp,
        "Twitch-Eventsub-Subscription-Type": "stream.online",
        "Twitch-Eventsub-Subscription-Version": "1",
    }
