"""YouTube push notifications over WebSub (T28c; checked 2026-10-31 in
https://developers.google.com/youtube/data/guides/push_notifications and
https://www.w3.org/TR/websub/, docs/decisions.md TASK-195).

With a public callback URL each enabled watched channel is subscribed at
the hub (POST hub.mode=subscribe, hub.topic, hub.callback, hub.secret,
hub.lease_seconds; the hub answers 202). The hub then checks the intent
with a GET to the callback (hub.mode, hub.topic, hub.challenge,
hub.lease_seconds): we echo the challenge only for a topic we asked for,
else 404. Notifications are POSTs of an Atom entry signed with
X-Hub-Signature: <method>=HMAC(secret, body); unsigned or badly signed ones
are refused (403), and those for a channel no longer watched get 410 so the
hub drops the subscription. Each topic has its own derived secret
(watch/keys). The subscription is renewed a day before its lease ends.
"""

import hashlib
import hmac
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx
from sqlalchemy import Engine

from clipforge.auto_import import set_channel_fields
from clipforge.models import PushState, WatchedChannel
from clipforge.watch.keys import derived_secret
from clipforge.watch.times import as_utc

HUB_URL = "https://pubsubhubbub.appspot.com/subscribe"
TOPIC_URL = "https://www.youtube.com/xml/feeds/videos.xml"
CALLBACK_PATH = "/api/watch/websub/"
LEASE_S = 10 * 24 * 3600
RENEW_BEFORE = timedelta(days=1)
PENDING_RETRY = timedelta(minutes=10)
FAILED_RETRY = timedelta(hours=1)
TIMEOUT = httpx.Timeout(20.0, connect=10.0)
SIGNATURE_METHODS = {"sha1", "sha256", "sha384", "sha512"}


class WebSubError(RuntimeError):
    """The hub refused or could not be reached; the message says why."""


def topic_url(channel_id: str) -> str:
    """Return the WebSub topic of a channel's uploads."""
    return f"{TOPIC_URL}?{urlencode({'channel_id': channel_id})}"


def callback_url(public_url: str, channel_id: str) -> str:
    """Return the callback the hub calls for a channel."""
    return f"{public_url.rstrip('/')}{CALLBACK_PATH}{channel_id}"


def topic_secret(channel_id: str, data_dir: Path | None = None) -> str:
    """Return the HMAC secret of the channel's subscription."""
    return derived_secret(f"websub:{channel_id}", data_dir)


def request_subscription(
    public_url: str,
    channel_id: str,
    *,
    mode: str = "subscribe",
    transport: httpx.BaseTransport | None = None,
    data_dir: Path | None = None,
) -> None:
    """Ask the hub to (un)subscribe the channel's callback; raise
    WebSubError unless it accepts (2xx)."""
    form = {
        "hub.callback": callback_url(public_url, channel_id),
        "hub.mode": mode,
        "hub.topic": topic_url(channel_id),
        "hub.verify": "async",
    }
    if mode == "subscribe":
        form["hub.lease_seconds"] = str(LEASE_S)
        form["hub.secret"] = topic_secret(channel_id, data_dir)
    try:
        with httpx.Client(transport=transport, timeout=TIMEOUT) as http:
            response = http.post(HUB_URL, data=form)
    except httpx.HTTPError as exc:
        raise WebSubError(f"could not reach the WebSub hub: {exc}") from exc
    if not response.is_success:
        detail = response.text.strip()[:200]
        raise WebSubError(
            f"the WebSub hub answered HTTP {response.status_code}"
            + (f": {detail}" if detail else "")
        )


def valid_signature(body: bytes, header: str | None, secret: str) -> bool:
    """Whether X-Hub-Signature (method=hexdigest) signs body with secret."""
    method, _, digest = (header or "").partition("=")
    method = method.strip().lower()
    if method not in SIGNATURE_METHODS or not digest:
        return False
    expected = hmac.new(secret.encode(), body, getattr(hashlib, method))
    return hmac.compare_digest(expected.hexdigest(), digest.strip().lower())


def needs_request(
    state: PushState,
    requested_at: datetime | None,
    lease_expires_at: datetime | None,
    now: datetime,
) -> bool:
    """Whether a push subscription should be asked for now: never asked, a
    request unanswered for 10 min, refused or failed an hour ago, or a
    lease that ends within a day."""
    if state == "off" or requested_at is None:
        return True
    asked = as_utc(requested_at)
    if state == "pending":
        return now - asked >= PENDING_RETRY
    if state == "subscribed":
        return (
            lease_expires_at is None or as_utc(lease_expires_at) - now <= RENEW_BEFORE
        )
    return now - asked >= FAILED_RETRY


def maintain(
    engine: Engine,
    channels: list[WatchedChannel],
    public_url: str,
    now: datetime,
    *,
    transport: httpx.BaseTransport | None = None,
    data_dir: Path | None = None,
) -> None:
    """Subscribe (or renew) the enabled channels that need it; with no
    public URL every subscription is off (polling only)."""
    for channel in channels:
        if not public_url:
            if channel.push_state != "off":
                set_channel_fields(
                    engine, channel.id, push_state="off", push_lease_expires_at=None
                )
            continue
        due = needs_request(
            channel.push_state,
            channel.push_requested_at,
            channel.push_lease_expires_at,
            now,
        )
        if not channel.enabled or not due:
            continue
        set_channel_fields(
            engine,
            channel.id,
            push_state="pending"
            if channel.push_state != "subscribed"
            else "subscribed",
            push_requested_at=now,
            push_error=None,
        )
        try:
            request_subscription(
                public_url, channel.channel_id, transport=transport, data_dir=data_dir
            )
        except WebSubError as exc:
            set_channel_fields(
                engine, channel.id, push_state="failed", push_error=str(exc)
            )


def verify_intent(
    engine: Engine,
    channel: WatchedChannel | None,
    channel_id: str,
    params: dict[str, str],
    now: datetime,
) -> str | None:
    """Answer the hub's intent check: return the challenge to echo, or None
    to refuse (404). A subscribe is confirmed for an enabled channel whose
    subscription we asked for, an unsubscribe for a channel no longer
    watched; a denial is recorded."""
    mode = params.get("hub.mode", "")
    if params.get("hub.topic") != topic_url(channel_id):
        return None
    watched = channel is not None and channel.enabled
    if mode == "denied":
        if channel is not None:
            reason = params.get("hub.reason", "")[:200] or "the hub denied it"
            set_channel_fields(
                engine, channel.id, push_state="denied", push_error=reason
            )
        return ""
    challenge = params.get("hub.challenge", "")
    if not challenge:
        return None
    if mode == "unsubscribe":
        return None if watched else challenge
    if mode != "subscribe" or channel is None or not watched:
        return None
    if channel.push_state not in ("pending", "subscribed"):
        return None
    lease = _lease_seconds(params.get("hub.lease_seconds", ""))
    set_channel_fields(
        engine,
        channel.id,
        push_state="subscribed",
        push_lease_expires_at=now + timedelta(seconds=lease),
        push_error=None,
    )
    return challenge


def _lease_seconds(value: str) -> int:
    try:
        lease = int(value)
    except ValueError:
        return LEASE_S
    return lease if lease > 0 else LEASE_S
