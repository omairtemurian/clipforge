"""Tests for YouTube's WebSub pushes (clipforge.watch.websub and
AutoImporter.receive_push): the hub subscription and its renewal, the
intent check, the signatures (403 without a valid one), 410 for a channel
no longer watched, and pushed duplicates ignored. respx stands in for the
hub; the pushed body is the recorded notification."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from clipforge.auto_import import (
    add_channel,
    get_channel,
    remove_channel,
    set_channel_fields,
)
from clipforge.models import WatchedChannel, WatchedChannelCreate
from clipforge.watch import websub
from clipforge.watch.events import list_events
from clipforge.watch.youtube_watcher import AutoImporter
from sqlalchemy import Engine
from watch_fakes import NEWEST_PUBLISHED, PUBLIC_URL, PUSH_NEWEST, hub_signature
from youtube_fakes import CHANNEL, NEWEST

NOW = datetime(2026, 10, 31, 14, 0, tzinfo=UTC)
TOPIC = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={CHANNEL}"
CALLBACK = f"{PUBLIC_URL}/api/watch/websub/{CHANNEL}"


@pytest.fixture
def channel(engine: Engine) -> WatchedChannel:
    added = add_channel(engine, WatchedChannelCreate(channel=CHANNEL))
    set_channel_fields(engine, added.id, created_at=NOW - timedelta(days=1))
    return get_channel(engine, added.id)


def _hub(respx_mock: respx.MockRouter, *answers: httpx.Response) -> respx.Route:
    return respx_mock.post(websub.HUB_URL).mock(side_effect=list(answers))


def _signed(body: bytes = PUSH_NEWEST, method: str = "sha1") -> str:
    return hub_signature(websub.topic_secret(CHANNEL), body, method)


def test_the_topic_and_callback_name_the_channel() -> None:
    assert websub.topic_url(CHANNEL) == TOPIC
    assert websub.callback_url(PUBLIC_URL + "/", CHANNEL) == CALLBACK


def test_maintain_subscribes_with_a_secret_and_a_ten_day_lease(
    engine: Engine, respx_mock: respx.MockRouter, channel: WatchedChannel
) -> None:
    hub = _hub(respx_mock, httpx.Response(202))

    websub.maintain(engine, [channel], PUBLIC_URL, NOW)

    form = parse_qs(hub.calls.last.request.content.decode())
    assert form["hub.mode"] == ["subscribe"]
    assert form["hub.topic"] == [TOPIC]
    assert form["hub.callback"] == [CALLBACK]
    assert form["hub.lease_seconds"] == ["864000"]
    secret = form["hub.secret"][0]
    assert secret == websub.topic_secret(CHANNEL) and len(secret.encode()) < 200
    pending = get_channel(engine, channel.id)
    assert (pending.push_state, pending.push_error) == ("pending", None)


def test_a_hub_error_is_kept_and_retried_after_an_hour(
    engine: Engine, respx_mock: respx.MockRouter, channel: WatchedChannel
) -> None:
    hub = _hub(respx_mock, httpx.Response(400, text="Invalid topic"))
    hub.side_effect = None
    hub.return_value = httpx.Response(400, text="Invalid topic")

    websub.maintain(engine, [channel], PUBLIC_URL, NOW)
    failed = get_channel(engine, channel.id)
    websub.maintain(engine, [failed], PUBLIC_URL, NOW + timedelta(minutes=59))

    assert failed.push_state == "failed"
    assert failed.push_error == "the WebSub hub answered HTTP 400: Invalid topic"
    assert hub.call_count == 1
    websub.maintain(engine, [failed], PUBLIC_URL, NOW + timedelta(hours=1))
    assert hub.call_count == 2


@pytest.mark.parametrize(
    ("state", "lease_days", "asked_minutes_ago", "asks"),
    [
        ("subscribed", 5, 60, False),
        ("subscribed", 0.5, 60, True),
        ("pending", None, 5, False),
        ("pending", None, 10, True),
        ("denied", None, 30, False),
        ("off", None, None, True),
    ],
)
def test_subscriptions_are_renewed_a_day_before_the_lease_ends(
    state: str, lease_days: float | None, asked_minutes_ago: int | None, asks: bool
) -> None:
    lease = NOW + timedelta(days=lease_days) if lease_days is not None else None
    asked = (
        NOW - timedelta(minutes=asked_minutes_ago)
        if asked_minutes_ago is not None
        else None
    )
    assert websub.needs_request(state, asked, lease, NOW) is asks  # type: ignore[arg-type]


def test_without_a_public_url_the_push_is_off(
    engine: Engine, respx_mock: respx.MockRouter, channel: WatchedChannel
) -> None:
    set_channel_fields(engine, channel.id, push_state="subscribed")

    websub.maintain(engine, [get_channel(engine, channel.id)], "", NOW)

    assert get_channel(engine, channel.id).push_state == "off"


def _params(mode: str = "subscribe", topic: str = TOPIC) -> dict[str, str]:
    return {
        "hub.mode": mode,
        "hub.topic": topic,
        "hub.challenge": "c-123",
        "hub.lease_seconds": "432000",
    }


def test_the_intent_check_of_a_requested_subscription_is_confirmed(
    engine: Engine, channel: WatchedChannel
) -> None:
    set_channel_fields(engine, channel.id, push_state="pending")
    pending = get_channel(engine, channel.id)

    challenge = websub.verify_intent(engine, pending, CHANNEL, _params(), NOW)

    assert challenge == "c-123"
    subscribed = get_channel(engine, channel.id)
    assert subscribed.push_state == "subscribed"
    assert subscribed.push_lease_expires_at == NOW + timedelta(days=5)


def test_intent_checks_we_did_not_ask_for_are_refused(
    engine: Engine, channel: WatchedChannel
) -> None:
    other = TOPIC.replace(CHANNEL, "UC" + "x" * 22)

    assert websub.verify_intent(engine, channel, CHANNEL, _params(), NOW) is None
    set_channel_fields(engine, channel.id, push_state="pending")
    pending = get_channel(engine, channel.id)
    assert (
        websub.verify_intent(engine, pending, CHANNEL, _params(topic=other), NOW)
        is None
    )
    assert websub.verify_intent(engine, None, CHANNEL, _params(), NOW) is None
    unsubscribe = _params("unsubscribe")
    assert websub.verify_intent(engine, pending, CHANNEL, unsubscribe, NOW) is None
    remove_channel(engine, channel.id)
    assert websub.verify_intent(engine, None, CHANNEL, unsubscribe, NOW) == "c-123"


def test_a_denial_is_recorded(engine: Engine, channel: WatchedChannel) -> None:
    params = {"hub.mode": "denied", "hub.topic": TOPIC, "hub.reason": "nope"}

    assert websub.verify_intent(engine, channel, CHANNEL, params, NOW) == ""

    denied = get_channel(engine, channel.id)
    assert (denied.push_state, denied.push_error) == ("denied", "nope")


@pytest.mark.parametrize("method", ["sha1", "sha256", "sha512"])
def test_signatures_are_checked(method: str) -> None:
    secret = websub.topic_secret(CHANNEL)
    good = hub_signature(secret, PUSH_NEWEST, method)

    assert websub.valid_signature(PUSH_NEWEST, good, secret)
    assert not websub.valid_signature(PUSH_NEWEST + b" ", good, secret)
    assert not websub.valid_signature(PUSH_NEWEST, good, secret + "x")
    assert not websub.valid_signature(PUSH_NEWEST, None, secret)
    assert not websub.valid_signature(PUSH_NEWEST, "md5=abc", secret)


def test_a_signed_push_imports_the_video_once(
    engine: Engine, channel: WatchedChannel
) -> None:
    woken: list[bool] = []
    importer = AutoImporter(
        engine, wall_clock=lambda: NOW, on_import=lambda: woken.append(True)
    )

    answer = importer.receive_push(CHANNEL, PUSH_NEWEST, _signed())
    again = importer.receive_push(CHANNEL, PUSH_NEWEST, _signed(method="sha256"))

    assert answer.status == 204 and len(answer.imported) == 1
    assert (again.status, again.imported) == (204, ())
    (event,) = list_events(engine)
    assert (event.external_id, event.via, event.project_id) == (
        NEWEST,
        "push",
        answer.imported[0],
    )
    assert event.published_at == NEWEST_PUBLISHED
    assert woken == [True]


def test_unsigned_or_unknown_pushes_are_refused(
    engine: Engine, channel: WatchedChannel
) -> None:
    importer = AutoImporter(engine)
    forged = hub_signature("not-the-secret", PUSH_NEWEST)

    assert importer.receive_push(CHANNEL, PUSH_NEWEST, None).status == 403
    assert importer.receive_push(CHANNEL, PUSH_NEWEST, forged).status == 403
    assert importer.receive_push(CHANNEL, b"<html/>", _signed(b"<html/>")).status == 400
    other = "UC" + "y" * 22
    assert importer.receive_push(other, PUSH_NEWEST, _signed()).status == 410
    set_channel_fields(engine, channel.id, enabled=False)
    assert importer.receive_push(CHANNEL, PUSH_NEWEST, _signed()).status == 410
    assert list_events(engine) == []


def test_a_push_of_a_video_older_than_the_channel_is_not_imported(
    engine: Engine, channel: WatchedChannel
) -> None:
    set_channel_fields(engine, channel.id, created_at=NEWEST_PUBLISHED + timedelta(1))

    answer = AutoImporter(engine).receive_push(CHANNEL, PUSH_NEWEST, _signed())

    assert (answer.status, answer.imported) == (204, ())
    assert list_events(engine) == []
