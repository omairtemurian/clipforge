"""Tests for the Twitch go-live watch (clipforge.watch.twitch_api,
twitch_eventsub and twitch_watcher): the app token, missing keys, polling
Get Streams, the stream.online EventSub webhook (recorded payloads, signed
like Twitch does), replays and bad signatures, revocations, and one alert
per stream however it was detected. respx stands in for Twitch."""

import json
import random
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from clipforge.models import WatchedStreamer, WatchedStreamerCreate
from clipforge.watch import twitch_eventsub
from clipforge.watch.events import list_events
from clipforge.watch.streamers import (
    add_streamer,
    list_streamers,
    set_streamer_fields,
)
from clipforge.watch.twitch_api import HELIX_URL, TOKEN_URL, TwitchApp
from clipforge.watch.twitch_watcher import TwitchWatcher
from fake_clock import FakeClock
from sqlalchemy import Engine
from watch_fakes import (
    LOGIN,
    PUBLIC_URL,
    STREAM_ID,
    TWITCH,
    USER_ID,
    WallClock,
    eventsub_headers,
    twitch_response,
)

NOW = datetime(2021, 3, 10, 3, 18, 40, tzinfo=UTC)
STARTED = datetime(2021, 3, 10, 3, 18, 11, tzinfo=UTC)


@pytest.fixture
def streamer(engine: Engine) -> WatchedStreamer:
    return add_streamer(engine, WatchedStreamerCreate(login="https://twitch.tv/Afro"))


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def _watcher(
    engine: Engine, clock: FakeClock, *, keys: bool = True, public_url: str = ""
) -> TwitchWatcher:
    app = TwitchApp("cid", "csecret" if keys else "", clock=clock)
    return TwitchWatcher(
        engine,
        app,
        clock=clock,
        rng=random.Random(5),
        wall_clock=WallClock(clock, NOW),
        public_url=public_url,
    )


def _twitch(respx_mock: respx.MockRouter) -> dict[str, respx.Route]:
    return {
        "token": respx_mock.post(TOKEN_URL).mock(return_value=twitch_response("token")),
        "users": respx_mock.get(f"{HELIX_URL}/users").mock(
            return_value=twitch_response("users")
        ),
        "streams": respx_mock.get(f"{HELIX_URL}/streams"),
        "subscribe": respx_mock.post(f"{HELIX_URL}/eventsub/subscriptions").mock(
            return_value=twitch_response("subscription_created", 202)
        ),
    }


def _message(
    name: str, kind: str, sent: datetime = NOW
) -> tuple[dict[str, str], bytes]:
    body = (TWITCH / f"{name}.json").read_bytes()
    secret = twitch_eventsub.eventsub_secret()
    return eventsub_headers(secret, body, kind, sent), body


def test_without_app_keys_nothing_is_asked(
    engine: Engine,
    respx_mock: respx.MockRouter,
    streamer: WatchedStreamer,
    clock: FakeClock,
) -> None:
    watcher = _watcher(engine, clock, keys=False)

    assert watcher.tick() == [] and watcher.poll() == []
    assert not watcher.app.configured
    assert len(respx_mock.calls) == 0
    assert list_streamers(engine)[0].last_error is None


def test_a_poll_resolves_the_login_and_reports_the_go_live_once(
    engine: Engine,
    respx_mock: respx.MockRouter,
    streamer: WatchedStreamer,
    clock: FakeClock,
) -> None:
    routes = _twitch(respx_mock)
    routes["streams"].side_effect = [
        twitch_response("streams_offline"),
        twitch_response("streams_live"),
        twitch_response("streams_live"),
        twitch_response("streams_offline"),
    ]
    watcher = _watcher(engine, clock)
    assert streamer.login == LOGIN

    watcher.tick()
    resolved = list_streamers(engine)[0]
    assert (resolved.user_id, resolved.display_name) == (USER_ID, "Afro")
    assert resolved.live_since is None and list_events(engine) == []
    request = routes["streams"].calls.last.request
    assert request.url.params.get_list("user_id") == [USER_ID]
    assert request.headers["authorization"] == "Bearer jostpf5q0uzmxmkba9iyug38kjtgh"
    assert request.headers["client-id"] == "cid"

    clock.now = watcher.schedule.next_due(LOGIN)
    watcher.tick()
    live = list_streamers(engine)[0]
    assert live.live_since == STARTED == live.last_live_at
    for _ in range(2):  # still live, then offline
        clock.now = watcher.schedule.next_due(LOGIN)
        watcher.tick()

    (event,) = list_events(engine)
    assert (event.platform, event.kind, event.external_id, event.via) == (
        "twitch",
        "live",
        STREAM_ID,
        "poll",
    )
    assert (event.source_name, event.url) == ("Afro", "https://www.twitch.tv/afro")
    assert event.published_at == STARTED and event.detected_at > STARTED
    offline = list_streamers(engine)[0]
    assert offline.live_since is None and offline.last_live_at == STARTED
    assert routes["token"].call_count == 1 and routes["users"].call_count == 1


def test_the_app_token_is_renewed_after_a_401(
    respx_mock: respx.MockRouter, clock: FakeClock
) -> None:
    routes = _twitch(respx_mock)
    routes["streams"].side_effect = [
        httpx.Response(401, json={"message": "Invalid OAuth token"}),
        twitch_response("streams_live"),
    ]
    app = TwitchApp("cid", "csecret", clock=clock)

    (stream,) = app.live_streams([USER_ID])

    assert stream["id"] == STREAM_ID
    assert routes["token"].call_count == 2
    form = routes["token"].calls.last.request.content.decode()
    assert "grant_type=client_credentials" in form


def test_twitch_errors_are_kept_and_backed_off(
    engine: Engine,
    respx_mock: respx.MockRouter,
    streamer: WatchedStreamer,
    clock: FakeClock,
) -> None:
    routes = _twitch(respx_mock)
    routes["users"].mock(return_value=httpx.Response(503, json={"message": "down"}))
    watcher = _watcher(engine, clock)

    watcher.tick()

    (failed,) = list_streamers(engine)
    assert failed.last_error == "Twitch /users answered HTTP 503: down"
    assert 108 <= watcher.schedule.next_due(LOGIN) - clock.now <= 132


def test_an_unknown_login_says_so(
    engine: Engine, respx_mock: respx.MockRouter, clock: FakeClock
) -> None:
    routes = _twitch(respx_mock)
    routes["users"].mock(return_value=httpx.Response(200, json={"data": []}))
    add_streamer(engine, WatchedStreamerCreate(login="nobody_here"))

    _watcher(engine, clock).tick()

    assert (
        list_streamers(engine)[0].last_error == "Twitch has no user named nobody_here"
    )


def test_with_a_public_url_stream_online_is_subscribed_and_verified(
    engine: Engine,
    respx_mock: respx.MockRouter,
    streamer: WatchedStreamer,
    clock: FakeClock,
) -> None:
    routes = _twitch(respx_mock)
    routes["streams"].mock(return_value=twitch_response("streams_offline"))
    watcher = _watcher(engine, clock, public_url=PUBLIC_URL)

    watcher.tick()

    body = json.loads(routes["subscribe"].calls.last.request.content)
    assert body["type"] == "stream.online" and body["version"] == "1"
    assert body["condition"] == {"broadcaster_user_id": USER_ID}
    assert body["transport"] == {
        "method": "webhook",
        "callback": f"{PUBLIC_URL}/api/watch/twitch/eventsub",
        "secret": twitch_eventsub.eventsub_secret(),
    }
    assert 10 <= len(body["transport"]["secret"]) <= 100
    assert list_streamers(engine)[0].push_state == "pending"

    headers, raw = _message("verification", "webhook_callback_verification")
    answer = watcher.handle_eventsub(headers, raw)

    assert (answer.status, answer.body) == (200, "pogchamp-kappa-360noscope-vohiyo")
    subscribed = list_streamers(engine)[0]
    assert subscribed.push_state == "subscribed"
    assert subscribed.subscription_id == "f1c2a387-161a-49f9-a165-0f21d7a4e1c4"
    clock.now = watcher.schedule.next_due(LOGIN)
    watcher.tick()
    assert 810 <= watcher.schedule.next_due(LOGIN) - clock.now <= 990
    assert routes["subscribe"].call_count == 1


def test_a_pushed_stream_online_is_one_alert_with_a_poll_of_it(
    engine: Engine,
    respx_mock: respx.MockRouter,
    streamer: WatchedStreamer,
    clock: FakeClock,
) -> None:
    routes = _twitch(respx_mock)
    routes["streams"].mock(return_value=twitch_response("streams_live"))
    watcher = _watcher(engine, clock)
    watcher.app.users([LOGIN])  # warm the token
    set_streamer_fields(engine, streamer.id, user_id=USER_ID)
    headers, raw = _message("stream_online", "notification")

    assert watcher.handle_eventsub(headers, raw).status == 204
    assert watcher.handle_eventsub(headers, raw).status == 204  # a retry
    watcher.tick()

    (event,) = list_events(engine)
    assert (event.external_id, event.via, event.source_name) == (
        STREAM_ID,
        "push",
        "Afro",
    )
    assert event.detected_at == NOW
    assert list_streamers(engine)[0].live_since is not None


def test_forged_or_replayed_messages_are_refused(
    engine: Engine, streamer: WatchedStreamer, clock: FakeClock
) -> None:
    watcher = _watcher(engine, clock)
    headers, raw = _message("stream_online", "notification")
    old_headers, _ = _message(
        "stream_online", "notification", NOW - timedelta(minutes=11)
    )
    forged = dict(headers)
    forged["Twitch-Eventsub-Message-Signature"] = "sha256=" + "0" * 64

    assert watcher.handle_eventsub(forged, raw).status == 403
    assert watcher.handle_eventsub(old_headers, raw).status == 403
    assert watcher.handle_eventsub(headers, raw + b" ").status == 403
    unsigned = {k: v for k, v in headers.items() if "Signature" not in k}
    assert watcher.handle_eventsub(unsigned, raw).status == 403
    assert list_events(engine) == []


def test_a_revocation_is_recorded_and_unknown_verifications_refused(
    engine: Engine, streamer: WatchedStreamer, clock: FakeClock
) -> None:
    watcher = _watcher(engine, clock)
    headers, raw = _message("verification", "webhook_callback_verification")
    assert watcher.handle_eventsub(headers, raw).status == 404  # id not known

    set_streamer_fields(engine, streamer.id, user_id=USER_ID, push_state="subscribed")
    headers, raw = _message("revocation", "revocation")

    assert watcher.handle_eventsub(headers, raw).status == 204
    revoked = list_streamers(engine)[0]
    assert revoked.push_state == "revoked"
    assert revoked.push_error == (
        "Twitch revoked the subscription: authorization_revoked"
    )
