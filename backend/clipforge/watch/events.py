"""The watch's alerts (watch_event rows): a new upload or a go-live, each
recorded once per (platform, kind, external id)."""

from datetime import datetime

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from clipforge.channel_rows import WatchEventRow
from clipforge.models import DetectedVia, WatchEvent, WatchEventKind, WatchPlatform

EVENTS_LIMIT = 50


def record_event(
    engine: Engine,
    *,
    platform: WatchPlatform,
    kind: WatchEventKind,
    external_id: str,
    detected_at: datetime,
    via: DetectedVia,
    source_name: str = "",
    title: str = "",
    url: str = "",
    project_id: int | None = None,
    published_at: datetime | None = None,
) -> WatchEvent | None:
    """Record an alert; return it, or None if it was already recorded (a
    duplicate notification)."""
    row = WatchEventRow(
        platform=platform,
        kind=kind,
        external_id=external_id,
        source_name=source_name,
        title=title,
        url=url,
        project_id=project_id,
        published_at=published_at,
        detected_at=detected_at,
        via=via,
    )
    with Session(engine) as session:
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            return None
        session.refresh(row)
        return row.to_model()


def list_events(
    engine: Engine, *, after: int = 0, limit: int = EVENTS_LIMIT
) -> list[WatchEvent]:
    """Return up to limit alerts with an id above after, newest first."""
    with Session(engine) as session:
        rows = session.exec(
            select(WatchEventRow)
            .where(col(WatchEventRow.id) > after)
            .order_by(col(WatchEventRow.id).desc())
            .limit(limit)
        )
        return [row.to_model() for row in rows]
