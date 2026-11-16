"""Sending the webhook deliveries (SPEC-v2 3.14): signing, one attempt, and
the retries with backoff, by a worker in the app's process.

Each attempt POSTs the JSON body

    {"id": <delivery id>, "event": "post.published", "created_at": "...Z",
     "data": {...}}

(compact, keys sorted) with the headers X-ClipForge-Event,
X-ClipForge-Delivery (the id), X-ClipForge-Timestamp (Unix seconds of this
attempt) and X-ClipForge-Signature: "sha256=" plus the hex HMAC-SHA256,
keyed with the webhook's secret, of "<timestamp>.<body>". A receiver
recomputes it and compares in constant time (verify_signature) and may
refuse an old timestamp (replay). Any 2xx answer delivers the event. Any
other answer, a timeout or a connection error is a failed attempt: the
n-th retry waits RETRY.delay(n) (30 s, 1 min, 2 min, ... at most 1 h) and
the RETRY.max_attempts-th failure is final. Redirects are not followed.
Every attempt updates the delivery row (the log the API shows): attempts,
time, HTTP status and error. At-least-once: an attempt that the app's stop
cut off is sent again, so receivers should deduplicate on the delivery id.
"""

import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta

import httpx
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge import webhooks
from clipforge.models import DeliveryStatus, WebhookDelivery
from clipforge.poller import Poller
from clipforge.scheduler.retry import RetryPolicy
from clipforge.watch.times import as_utc, utc_now
from clipforge.webhook_rows import WebhookDeliveryRow, WebhookRow

logger = logging.getLogger(__name__)

EVENT_HEADER = "X-ClipForge-Event"
DELIVERY_HEADER = "X-ClipForge-Delivery"
TIMESTAMP_HEADER = "X-ClipForge-Timestamp"
SIGNATURE_HEADER = "X-ClipForge-Signature"
SIGNATURE_PREFIX = "sha256="

RETRY = RetryPolicy(6, timedelta(seconds=30), timedelta(hours=1))
TIMEOUT_S = 10.0
POLL_S = 2.0
BATCH = 50
# How old a timestamp may be for verify_signature (seconds).
TOLERANCE_S = 300


def body_of(delivery: WebhookDelivery) -> bytes:
    """Return the JSON body that delivery sends (the same on every attempt)."""
    body = {
        "id": delivery.id,
        "event": delivery.event,
        "created_at": delivery.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data": delivery.data,
    }
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode()


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """Return the signature header value of body sent at Unix time timestamp."""
    message = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + digest


def verify_signature(
    secret: str,
    timestamp: int,
    body: bytes,
    signature: str,
    now: datetime,
    tolerance: int = TOLERANCE_S,
) -> bool:
    """Return whether signature is the signature of body and timestamp and
    the timestamp is within tolerance seconds of now (what a receiver
    checks; docs/automation.md shows it in Python and Node)."""
    if abs(now.timestamp() - timestamp) > tolerance:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature)


class WebhookWorker(Poller):
    """Sends the due deliveries every interval seconds. now is the wall
    clock of due times and backoff, clock (monotonic) paces the polls;
    client sends the requests (tests pass one on a mock transport)."""

    thread_name = "clipforge-webhook-worker"

    def __init__(
        self,
        engine: Engine,
        *,
        interval: float = POLL_S,
        retry: RetryPolicy = RETRY,
        client: httpx.Client | None = None,
        now: Callable[[], datetime] = utc_now,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(interval=interval, clock=clock)
        self.engine = engine
        self.retry = retry
        self.client = client or httpx.Client(timeout=TIMEOUT_S)
        self.now = now

    def poll(self) -> list[int]:
        """Make one attempt for each due delivery (oldest first, at most
        BATCH); return the ids of those that were delivered."""
        delivered = []
        for delivery_id in self.due(self.now()):
            if self._stop.is_set():
                break
            if self.deliver(delivery_id):
                delivered.append(delivery_id)
        return delivered

    def due(self, now: datetime) -> list[int]:
        """Return the ids of the pending deliveries whose time has come."""
        with Session(self.engine) as session:
            ids = session.exec(
                select(WebhookDeliveryRow.id)
                .where(
                    col(WebhookDeliveryRow.status) == "pending",
                    col(WebhookDeliveryRow.next_attempt_at) <= as_utc(now),
                )
                .order_by(col(WebhookDeliveryRow.id))
                .limit(BATCH)
            )
            return [delivery_id for delivery_id in ids if delivery_id is not None]

    def deliver(self, delivery_id: int) -> bool:
        """Make one attempt for the pending delivery; return whether the
        endpoint took it. A failure schedules the next attempt, or fails
        the delivery if it was the last."""
        moment = self.now()
        with Session(self.engine) as session:
            row = session.get(WebhookDeliveryRow, delivery_id)
            hook = None if row is None else session.get(WebhookRow, row.webhook_id)
            if row is None or row.status != "pending":
                return False
            if hook is None or not hook.enabled:
                row.status = "failed"
                row.next_attempt_at = None
                row.error = "The webhook is deleted or disabled."
                session.add(row)
                session.commit()
                return False
            delivery = row.to_model()
            url, secret = hook.url, webhooks.secret_of(hook)
        status, error = self._send(url, secret, delivery, moment)
        with Session(self.engine) as session:
            row = session.get(WebhookDeliveryRow, delivery_id)
            if row is None:
                return False
            if status is not None and 200 <= status < 300:
                self._finish(row, "delivered", moment, status)
            elif self.retry.gives_up(row.attempts + 1):
                self._finish(row, "failed", moment, status, error)
            else:
                delay = self.retry.delay(row.attempts + 1)
                self._finish(row, "pending", moment, status, error, moment + delay)
            session.add(row)
            session.commit()
            return row.status == "delivered"

    def _send(
        self, url: str, secret: str, delivery: WebhookDelivery, moment: datetime
    ) -> tuple[int | None, str | None]:
        """POST delivery to url; return the HTTP status (None if there was
        no answer) and the error to log (None for a 2xx answer)."""
        body = body_of(delivery)
        timestamp = int(moment.timestamp())
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ClipForge-Webhook/1",
            EVENT_HEADER: delivery.event,
            DELIVERY_HEADER: str(delivery.id),
            TIMESTAMP_HEADER: str(timestamp),
            SIGNATURE_HEADER: sign(secret, timestamp, body),
        }
        try:
            response = self.client.post(url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.info("delivery %d: no answer: %s", delivery.id, type(exc).__name__)
            return None, f"No answer: {type(exc).__name__}: {exc}"[:500]
        if response.is_success:
            return response.status_code, None
        logger.info("delivery %d: answered %d", delivery.id, response.status_code)
        return response.status_code, f"The endpoint answered {response.status_code}."

    @staticmethod
    def _finish(
        row: WebhookDeliveryRow,
        status: DeliveryStatus,
        moment: datetime,
        response_status: int | None = None,
        error: str | None = None,
        retry_at: datetime | None = None,
    ) -> None:
        """Record an attempt at moment on row: its new status, the answer
        and when to try again."""
        row.status = status
        row.attempts += 1
        row.attempted_at = moment
        row.next_attempt_at = retry_at
        row.response_status = response_status
        row.error = error
