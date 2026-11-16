"""SQLModel rows of the webhooks and their delivery log (migration
021_v2_webhooks); to_model() returns the matching model of
clipforge.models."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Index
from sqlmodel import AutoString, Field, SQLModel

from clipforge.db import PydanticJSON
from clipforge.models import DeliveryStatus, Webhook, WebhookDelivery, WebhookEvent
from clipforge.watch.times import as_utc


class WebhookRow(SQLModel, table=True):
    """A row of the webhook table; events is JSON and secret_enc the
    encrypted signing secret."""

    __tablename__ = "webhook"

    id: int | None = Field(default=None, primary_key=True)
    url: str
    events: list[WebhookEvent] = Field(
        default_factory=list, sa_type=PydanticJSON(list[WebhookEvent])
    )
    secret_enc: str
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_model(self) -> Webhook:
        """Return this row as a Webhook (without its secret), time in UTC."""
        return Webhook(
            id=self.id or 0,
            url=self.url,
            events=self.events,
            enabled=self.enabled,
            created_at=as_utc(self.created_at),
        )


class WebhookDeliveryRow(SQLModel, table=True):
    """A row of the webhook_delivery table; data is JSON."""

    __tablename__ = "webhook_delivery"
    __table_args__ = (Index("webhook_delivery_due", "status", "next_attempt_at"),)

    id: int | None = Field(default=None, primary_key=True)
    webhook_id: int = Field(foreign_key="webhook.id", ondelete="CASCADE")
    event: WebhookEvent = Field(sa_type=AutoString)
    data: dict[str, Any] = Field(
        default_factory=dict, sa_type=PydanticJSON(dict[str, Any])
    )
    status: DeliveryStatus = Field(default="pending", sa_type=AutoString)
    attempts: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    attempted_at: datetime | None = None
    next_attempt_at: datetime | None = None
    response_status: int | None = None
    error: str | None = None

    def to_model(self) -> WebhookDelivery:
        """Return this row as a WebhookDelivery, times in UTC."""
        return WebhookDelivery(
            id=self.id or 0,
            webhook_id=self.webhook_id,
            event=self.event,
            data=self.data,
            status=self.status,
            attempts=self.attempts,
            created_at=as_utc(self.created_at),
            attempted_at=None
            if self.attempted_at is None
            else as_utc(self.attempted_at),
            next_attempt_at=(
                None if self.next_attempt_at is None else as_utc(self.next_attempt_at)
            ),
            response_status=self.response_status,
            error=self.error,
        )
