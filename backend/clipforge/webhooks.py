"""Webhooks of the automation API (SPEC-v2 3.14, 4): the owner registers
endpoints that ClipForge POSTs its events to.

A webhook has a url and the events it wants (models.WEBHOOK_EVENTS:
project.completed, clip.rendered, post.published, post.failed). Its secret,
"whsec_" plus 43 URL-safe characters, is returned once, by create_webhook.
Signing a delivery with HMAC-SHA256 needs the secret itself, so the
spec's "secret_hash" cannot be a hash: the webhook table keeps the secret
encrypted (Fernet, key derived from the data directory's master key,
purpose "webhook-secrets") and only webhook_delivery reads it back, to sign
(docs/decisions.md, TASK-165).

emit() does not send anything: it writes a pending delivery for each enabled
webhook that wants the event, and the WebhookWorker (webhook_delivery) sends
them, retrying with backoff, so a slow or dead endpoint never holds up a job
or a post.
"""

import logging
import secrets
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge import config
from clipforge.models import (
    Webhook,
    WebhookCreated,
    WebhookDelivery,
    WebhookEvent,
    WebhookUpdate,
)
from clipforge.token_store import fernet_for
from clipforge.watch.times import utc_now
from clipforge.webhook_rows import WebhookDeliveryRow, WebhookRow

logger = logging.getLogger(__name__)

SECRET_PREFIX = "whsec_"
SECRET_BYTES = 32
SECRET_PURPOSE = "webhook-secrets"


class WebhookNotFound(LookupError):
    """There is no such webhook."""


def _fernet() -> Fernet:
    return fernet_for(config.settings.data_dir, SECRET_PURPOSE)


def secret_of(row: WebhookRow) -> str:
    """Return the signing secret of the webhook row."""
    return _fernet().decrypt(row.secret_enc.encode()).decode()


def create_webhook(
    engine: Engine, url: str, events: list[WebhookEvent]
) -> WebhookCreated:
    """Register a webhook; the result holds its secret, which cannot be read
    back through the API later."""
    secret = SECRET_PREFIX + secrets.token_urlsafe(SECRET_BYTES)
    row = WebhookRow(
        url=url, events=events, secret_enc=_fernet().encrypt(secret.encode()).decode()
    )
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return WebhookCreated(**row.to_model().model_dump(), secret=secret)


def list_webhooks(engine: Engine) -> list[Webhook]:
    """Return every webhook (without secrets), oldest first."""
    with Session(engine) as session:
        rows = session.exec(select(WebhookRow).order_by(col(WebhookRow.id)))
        return [row.to_model() for row in rows]


def get_webhook(engine: Engine, webhook_id: int) -> Webhook:
    """Return the webhook; WebhookNotFound if there is none."""
    with Session(engine) as session:
        return _row(session, webhook_id).to_model()


def update_webhook(engine: Engine, webhook_id: int, change: WebhookUpdate) -> Webhook:
    """Apply the fields that change sets; WebhookNotFound if there is none."""
    with Session(engine) as session:
        row = _row(session, webhook_id)
        for field, value in change.model_dump(exclude_none=True).items():
            setattr(row, field, value)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def delete_webhook(engine: Engine, webhook_id: int) -> None:
    """Delete the webhook and its delivery log; WebhookNotFound if none."""
    with Session(engine) as session:
        session.delete(_row(session, webhook_id))
        session.commit()


def list_deliveries(
    engine: Engine, webhook_id: int, limit: int = 50
) -> list[WebhookDelivery]:
    """Return the latest limit deliveries of the webhook, newest first;
    WebhookNotFound if there is no such webhook."""
    with Session(engine) as session:
        _row(session, webhook_id)
        rows = session.exec(
            select(WebhookDeliveryRow)
            .where(col(WebhookDeliveryRow.webhook_id) == webhook_id)
            .order_by(col(WebhookDeliveryRow.id).desc())
            .limit(limit)
        )
        return [row.to_model() for row in rows]


def emit(
    engine: Engine,
    event: WebhookEvent,
    data: dict[str, Any],
    now: datetime | None = None,
) -> list[int]:
    """Queue a delivery of event with payload data to each enabled webhook
    that wants it; return the delivery ids. Never raises: a failure to queue
    is logged, as the job or post that caused the event must go on."""
    moment = now or utc_now()
    try:
        with Session(engine) as session:
            hooks = session.exec(
                select(WebhookRow).where(col(WebhookRow.enabled).is_(True))
            ).all()
            queued = [
                WebhookDeliveryRow(
                    webhook_id=hook.id or 0,
                    event=event,
                    data=data,
                    created_at=moment,
                    next_attempt_at=moment,
                )
                for hook in hooks
                if event in hook.events
            ]
            session.add_all(queued)
            session.commit()
            return [row.id or 0 for row in queued]
    except Exception:
        logger.exception("could not queue the webhook event %s", event)
        return []


def _row(session: Session, webhook_id: int) -> WebhookRow:
    row = session.get(WebhookRow, webhook_id)
    if row is None:
        raise WebhookNotFound(f"webhook {webhook_id} does not exist")
    return row
