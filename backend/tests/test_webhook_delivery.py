"""Tests of the webhook deliveries (clipforge.webhook_delivery): the HMAC
signature, what is sent, retries with exponential backoff on a fake wall
clock (respx: the endpoint is made up) and the delivery log."""

import json
from datetime import timedelta

import httpx
import pytest
import respx
from clipforge import webhooks
from clipforge.models import WebhookUpdate
from clipforge.webhook_delivery import (
    body_of,
    sign,
    verify_signature,
)
from fake_clock import FakeWallClock
from sqlalchemy import Engine
from webhook_fakes import (
    RETRY,
    START,
    URL,
    delivery_log,
    endpoint,
    expected_signature,
    make_worker,
    register,
)


@pytest.fixture
def clock() -> FakeWallClock:
    return FakeWallClock(START)


SECRET = "whsec_test"
BODY = b'{"data":{},"event":"clip.rendered","id":1}'


def test_the_signature_is_the_hmac_of_timestamp_dot_body() -> None:
    signature = sign(SECRET, 1900000000, BODY)

    assert signature == expected_signature(SECRET, "1900000000", BODY)
    assert signature.startswith("sha256=") and len(signature) == 71
    assert sign("whsec_other", 1900000000, BODY) != signature
    assert sign(SECRET, 1900000001, BODY) != signature


def test_a_receiver_checks_the_signature_and_the_age() -> None:
    now = START
    stamp = int(now.timestamp())
    signature = sign(SECRET, stamp, BODY)

    assert verify_signature(SECRET, stamp, BODY, signature, now)
    assert verify_signature(SECRET, stamp, BODY, signature, now + timedelta(minutes=5))
    assert not verify_signature(SECRET, stamp, BODY + b" ", signature, now)
    assert not verify_signature("whsec_other", stamp, BODY, signature, now)
    assert not verify_signature(SECRET, stamp, BODY, "sha256=00", now)
    late = now + timedelta(minutes=5, seconds=1)
    assert not verify_signature(SECRET, stamp, BODY, signature, late)


def test_a_delivery_is_a_signed_json_post(
    engine: Engine, clock: FakeWallClock, respx_mock: respx.MockRouter
) -> None:
    hook = register(engine)
    route = endpoint(respx_mock, 204)
    (delivery_id,) = webhooks.emit(
        engine, "clip.rendered", {"clip": {"id": 3, "t": "é"}}, START
    )

    assert make_worker(engine, clock).poll() == [delivery_id]

    (request,) = [call.request for call in route.calls]
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["X-ClipForge-Event"] == "clip.rendered"
    assert request.headers["X-ClipForge-Delivery"] == str(delivery_id)
    stamp = request.headers["X-ClipForge-Timestamp"]
    assert stamp == str(int(START.timestamp()))
    assert request.headers["X-ClipForge-Signature"] == expected_signature(
        hook.secret, stamp, request.content
    )
    assert json.loads(request.content) == {
        "id": delivery_id,
        "event": "clip.rendered",
        "created_at": "2030-01-15T09:00:00Z",
        "data": {"clip": {"id": 3, "t": "é"}},
    }
    (logged,) = delivery_log(engine, hook.id)
    assert (logged.status, logged.attempts, logged.response_status, logged.error) == (
        "delivered",
        1,
        204,
        None,
    )
    assert (logged.attempted_at, logged.next_attempt_at) == (START, None)


def test_the_body_is_the_same_on_every_attempt(engine: Engine) -> None:
    register(engine)
    webhooks.emit(engine, "post.failed", {"b": 1, "a": [2, {"d": 1, "c": 0}]})
    (delivery,) = delivery_log(engine, 1)

    assert body_of(delivery) == body_of(delivery)
    assert body_of(delivery) == (
        b'{"created_at":"%s","data":{"a":[2,{"c":0,"d":1}],"b":1},'
        b'"event":"post.failed","id":1}'
        % delivery.created_at.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    )


def test_failed_attempts_are_retried_with_exponential_backoff(
    engine: Engine, clock: FakeWallClock, respx_mock: respx.MockRouter
) -> None:
    hook = register(engine)
    route = endpoint(respx_mock, 500, 503, 200)
    webhooks.emit(engine, "post.published", {})
    worker = make_worker(engine, clock)

    assert worker.poll() == []
    (log,) = delivery_log(engine, hook.id)
    assert (log.status, log.attempts, log.response_status) == ("pending", 1, 500)
    assert log.error == "The endpoint answered 500."
    assert log.next_attempt_at == START + timedelta(seconds=10)

    clock.advance(seconds=9)
    assert worker.poll() == []
    assert route.call_count == 1
    clock.advance(seconds=1)
    assert worker.poll() == []
    (log,) = delivery_log(engine, hook.id)
    assert (log.attempts, log.response_status) == (2, 503)
    assert log.next_attempt_at == clock.now + timedelta(seconds=20)

    clock.advance(seconds=20)
    assert worker.poll() == [log.id]
    (log,) = delivery_log(engine, hook.id)
    assert (log.status, log.attempts, log.response_status, log.error) == (
        "delivered",
        3,
        200,
        None,
    )
    assert log.next_attempt_at is None
    assert route.call_count == 3
    clock.advance(hours=1)
    assert worker.poll() == []
    assert route.call_count == 3


def test_the_last_attempt_fails_the_delivery_for_good(
    engine: Engine, clock: FakeWallClock, respx_mock: respx.MockRouter
) -> None:
    hook = register(engine)
    route = endpoint(respx_mock, 500)
    webhooks.emit(engine, "post.failed", {})
    worker = make_worker(engine, clock)

    waits = []
    for _ in range(RETRY.max_attempts):
        worker.poll()
        (log,) = delivery_log(engine, hook.id)
        waits.append(log.next_attempt_at and log.next_attempt_at - clock.now)
        clock.advance(hours=1)
    worker.poll()

    assert waits == [
        timedelta(seconds=10),
        timedelta(seconds=20),
        timedelta(seconds=40),
        None,
    ]
    assert route.call_count == 4
    assert (log.status, log.attempts, log.response_status) == ("failed", 4, 500)
    assert log.next_attempt_at is None


def test_no_answer_is_a_failed_attempt_with_the_reason_logged(
    engine: Engine, clock: FakeWallClock, respx_mock: respx.MockRouter
) -> None:
    hook = register(engine)
    respx_mock.post(URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
    webhooks.emit(engine, "clip.rendered", {})

    make_worker(engine, clock).poll()

    (log,) = delivery_log(engine, hook.id)
    assert (log.status, log.attempts, log.response_status) == ("pending", 1, None)
    assert log.error == "No answer: ConnectTimeout: timed out"


def test_a_redirect_is_not_followed(
    engine: Engine, clock: FakeWallClock, respx_mock: respx.MockRouter
) -> None:
    hook = register(engine)
    respx_mock.post(URL).mock(
        return_value=httpx.Response(302, headers={"Location": "http://10.0.0.1/x"})
    )
    webhooks.emit(engine, "clip.rendered", {})

    make_worker(engine, clock).poll()

    (log,) = delivery_log(engine, hook.id)
    assert (log.status, log.response_status) == ("pending", 302)


def test_deliveries_go_out_oldest_first_each_with_its_own_log(
    engine: Engine, clock: FakeWallClock, respx_mock: respx.MockRouter
) -> None:
    hook = register(engine)
    route = endpoint(respx_mock, 200)
    first = webhooks.emit(engine, "clip.rendered", {"n": 1})
    second = webhooks.emit(engine, "post.failed", {"n": 2})

    assert make_worker(engine, clock).poll() == first + second

    events = [call.request.headers["X-ClipForge-Event"] for call in route.calls]
    assert events == ["clip.rendered", "post.failed"]
    assert [d.status for d in delivery_log(engine, hook.id)] == ["delivered"] * 2


def test_a_delivery_of_a_paused_webhook_fails_without_a_request(
    engine: Engine, clock: FakeWallClock, respx_mock: respx.MockRouter
) -> None:
    hook = register(engine)
    route = endpoint(respx_mock, 200)
    webhooks.emit(engine, "clip.rendered", {})
    webhooks.update_webhook(engine, hook.id, WebhookUpdate(enabled=False))

    assert make_worker(engine, clock).poll() == []

    assert route.call_count == 0
    (log,) = delivery_log(engine, hook.id)
    assert (log.status, log.attempts) == ("failed", 0)
    assert log.error == "The webhook is deleted or disabled."
