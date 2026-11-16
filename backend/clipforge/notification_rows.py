"""SQLModel row of the in-app notifications (migration 033_v2_notifications);
to_model() returns the matching model of clipforge.models."""

from datetime import UTC, datetime

from sqlmodel import AutoString, Field, SQLModel

from clipforge.models import Notification, NotificationKind
from clipforge.watch.times import as_utc


class NotificationRow(SQLModel, table=True):
    """A row of the notification table; dedupe_key is unique when set."""

    __tablename__ = "notification"

    id: int | None = Field(default=None, primary_key=True)
    kind: NotificationKind = Field(sa_type=AutoString)
    title: str
    body: str = ""
    link: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    read_at: datetime | None = None
    dedupe_key: str | None = Field(default=None, unique=True)

    def to_model(self) -> Notification:
        """Return this row as a Notification, times in UTC."""
        return Notification(
            id=self.id or 0,
            kind=self.kind,
            title=self.title,
            body=self.body,
            link=self.link,
            created_at=as_utc(self.created_at),
            read_at=None if self.read_at is None else as_utc(self.read_at),
        )
