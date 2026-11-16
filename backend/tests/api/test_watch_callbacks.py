"""Tests for the push callbacks over HTTP (api/watch_callbacks.py): the
WebSub intent check (the challenge echoed as octet-stream with nosniff, 404
for a topic we did not ask for), signed and unsigned YouTube pushes, and
the Twitch EventSub verification and notification."""

from datetime import UTC, datetime

from clipforge.auto_import import add_channel, get_channel, set_channel_fields
from clipforge.models import WatchedChannelCreate, WatchedStreamerCreate
from clipforge.watch import twitch_eventsub, websub
from clipforge.watch.events import list_events
from clipforge.watch.streamers import add_streamer, set_streamer_fields
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from watch_fakes import (
    PUSH_NEWEST,
    TWITCH,
    USER_ID,
    eventsub_headers,
    hub_signature,
)
from youtube_fakes import CHANNEL, NEWEST

CALLBACK = f"/api/watch/websub/{CHANNEL}"
EVENTSUB = "/api/watch/twitch/eventsub"


def _pending_channel(engine: Engine) -> int:
    channel = add_channel(engine, WatchedChannelCreate(channel=CHANNEL))
    set_channel_fields(
        engine,
        channel.id,
        push_state="pending",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    return channel.id


def test_the_hub_handshake_and_a_signed_push(
    client: TestClient, api_engine: Engine
) -> None:
    channel_id = _pending_channel(api_engine)
    params = {
        "hub.mode": "subscribe",
        "hub.topic": websub.topic_url(CHANNEL),
        "hub.challenge": "a-challenge-1",
        "hub.lease_seconds": "864000",
    }

    verified = client.get(CALLBACK, params=params)

    assert verified.status_code == 200 and verified.text == "a-challenge-1"
    assert verified.headers["content-type"] == "application/octet-stream"
    assert verified.headers["x-content-type-options"] == "nosniff"
    assert get_channel(api_engine, channel_id).push_state == "subscribed"
    wrong = {**params, "hub.topic": "https://evil.example.com/feed"}
    assert client.get(CALLBACK, params=wrong).status_code == 404

    signature = hub_signature(websub.topic_secret(CHANNEL), PUSH_NEWEST)
    unsigned = client.post(CALLBACK, content=PUSH_NEWEST)
    pushed = client.post(
        CALLBACK, content=PUSH_NEWEST, headers={"X-Hub-Signature": signature}
    )
    duplicate = client.post(
        CALLBACK, content=PUSH_NEWEST, headers={"X-Hub-Signature": signature}
    )

    assert unsigned.status_code == 403
    assert (pushed.status_code, duplicate.status_code) == (204, 204)
    (event,) = list_events(api_engine)
    assert (event.external_id, event.via) == (NEWEST, "push")
    gone = client.post(
        "/api/watch/websub/UC" + "z" * 22,
        content=PUSH_NEWEST,
        headers={"X-Hub-Signature": signature},
    )
    assert gone.status_code == 410


def test_the_twitch_verification_and_go_live(
    client: TestClient, api_engine: Engine
) -> None:
    streamer = add_streamer(api_engine, WatchedStreamerCreate(login="afro"))
    set_streamer_fields(api_engine, streamer.id, user_id=USER_ID, push_state="pending")
    secret = twitch_eventsub.eventsub_secret()
    now = datetime.now(UTC)

    body = (TWITCH / "verification.json").read_bytes()
    headers = eventsub_headers(secret, body, "webhook_callback_verification", now)
    verified = client.post(EVENTSUB, content=body, headers=headers)

    assert verified.status_code == 200
    assert verified.text == "pogchamp-kappa-360noscope-vohiyo"
    assert verified.headers["content-type"].startswith("text/plain")

    body = (TWITCH / "stream_online.json").read_bytes()
    headers = eventsub_headers(secret, body, "notification", now, "msg-2")
    assert client.post(EVENTSUB, content=body, headers=headers).status_code == 204
    headers["Twitch-Eventsub-Message-Signature"] = "sha256=" + "1" * 64
    assert client.post(EVENTSUB, content=body, headers=headers).status_code == 403

    (event,) = list_events(api_engine)
    assert (event.platform, event.kind, event.via) == ("twitch", "live", "push")
