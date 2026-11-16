"""Helpers of the webhook tests (tests only): registered webhooks, a
delivery worker on a fake wall clock, and the receiving endpoint (respx:
nothing leaves the machine)."""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import httpx
import respx
from clipforge import webhooks
from clipforge.models import WebhookCreated, WebhookDelivery, WebhookEvent
from clipforge.scheduler.retry import RetryPolicy
from clipforge.webhook_delivery import WebhookWorker
from fake_clock import FakeWallClock
from sqlalchemy import Engine

URL = "https://hooks.example.test/clipforge"
START = datetime(2030, 1, 15, 9, 0, tzinfo=UTC)
# 4 sends; the retries wait 10 s, 20 s and 40 s.
RETRY = RetryPolicy(4, timedelta(seconds=10), timedelta(seconds=40))
ALL_EVENTS: list[WebhookEvent] = [
    "project.completed",
    "clip.rendered",
    "post.published",
    "post.failed",
]


def register(
    engine: Engine, events: list[WebhookEvent] | None = None, url: str = URL
) -> WebhookCreated:
    """Register a webhook of events (default: all of them)."""
    return webhooks.create_webhook(engine, url, events or ALL_EVENTS)


def make_worker(
    engine: Engine, clock: FakeWallClock, retry: RetryPolicy = RETRY
) -> WebhookWorker:
    """A delivery worker on clock."""
    return WebhookWorker(
        engine, interval=1.0, retry=retry, client=httpx.Client(), now=clock
    )


def endpoint(respx_mock: respx.MockRouter, *answers: int) -> respx.Route:
    """Make the endpoint answer with the statuses in answers, one per
    request (the last one for any further request)."""
    statuses = iter(answers)

    def answer(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses, answers[-1]))

    return respx_mock.post(URL).mock(side_effect=answer)


def delivery_log(engine: Engine, webhook_id: int) -> list[WebhookDelivery]:
    """The deliveries of the webhook, oldest first."""
    return webhooks.list_deliveries(engine, webhook_id)[::-1]


def expected_signature(secret: str, timestamp: str, body: bytes) -> str:
    """The signature of the spec in docs/automation.md, computed here
    independently of the code under test."""
    message = timestamp.encode() + b"." + body
    return "sha256=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
