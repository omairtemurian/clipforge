"""Twitch EventSub webhook messages (T28c; checked 2026-10-31 in
https://dev.twitch.tv/docs/eventsub/handling-webhook-events,
docs/decisions.md TASK-195).

Twitch signs each message: Twitch-Eventsub-Message-Signature is "sha256="
and the hex HMAC-SHA256, with the subscription's secret, of the message id,
the timestamp and the raw body. A message with a bad signature, or older
than 10 minutes (a replay), is refused with 403. Message types:
webhook_callback_verification (answer 200 with the raw challenge as
text/plain), notification and revocation.
"""

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from clipforge.watch.keys import derived_secret
from clipforge.watch.times import as_utc

CALLBACK_PATH = "/api/watch/twitch/eventsub"
MESSAGE_ID = "twitch-eventsub-message-id"
MESSAGE_TIMESTAMP = "twitch-eventsub-message-timestamp"
MESSAGE_SIGNATURE = "twitch-eventsub-message-signature"
MESSAGE_TYPE = "twitch-eventsub-message-type"
MAX_AGE = timedelta(minutes=10)


@dataclass(frozen=True)
class EventSubAnswer:
    """The callback's HTTP answer to a message."""

    status: int
    body: str = ""


@dataclass(frozen=True)
class EventSubMessage:
    """A verified message: its type and JSON body."""

    type: str
    payload: dict[str, Any]

    @property
    def subscription(self) -> dict[str, Any]:
        """The message's subscription object."""
        value = self.payload.get("subscription")
        return value if isinstance(value, dict) else {}

    @property
    def broadcaster_id(self) -> str:
        """The broadcaster of the subscription's condition."""
        condition = self.subscription.get("condition")
        if not isinstance(condition, dict):
            return ""
        return str(condition.get("broadcaster_user_id", ""))


def callback_url(public_url: str) -> str:
    """Return the EventSub webhook callback of the app."""
    return f"{public_url.rstrip('/')}{CALLBACK_PATH}"


def eventsub_secret(data_dir: Path | None = None) -> str:
    """Return the secret of the app's EventSub subscriptions."""
    return derived_secret("twitch-eventsub", data_dir)


def signature(secret: str, message_id: str, timestamp: str, body: bytes) -> str:
    """Return the Twitch-Eventsub-Message-Signature of a message."""
    signed = message_id.encode() + timestamp.encode() + body
    return "sha256=" + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def read_message(
    headers: Mapping[str, str], body: bytes, secret: str, now: datetime
) -> EventSubMessage | None:
    """Return the message if it is signed with secret, recent and JSON;
    None otherwise (refuse it). Header names are case-insensitive."""
    headers = {name.lower(): value for name, value in headers.items()}
    message_id = headers.get(MESSAGE_ID, "")
    timestamp = headers.get(MESSAGE_TIMESTAMP, "")
    received = headers.get(MESSAGE_SIGNATURE, "")
    if not (message_id and timestamp and received):
        return None
    expected = signature(secret, message_id, timestamp, body)
    if not hmac.compare_digest(expected, received.strip().lower()):
        return None
    try:
        sent = as_utc(datetime.fromisoformat(timestamp))
        payload = json.loads(body)
    except ValueError:
        return None
    if abs(now - sent) > MAX_AGE or not isinstance(payload, dict):
        return None
    return EventSubMessage(headers.get(MESSAGE_TYPE, ""), payload)


def parse_time(value: object) -> datetime | None:
    """Parse an RFC 3339 time of a Twitch payload (None if bad)."""
    try:
        return as_utc(datetime.fromisoformat(str(value)))
    except ValueError:
        return None
