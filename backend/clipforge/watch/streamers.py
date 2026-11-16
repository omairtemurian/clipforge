"""The watched Twitch streamers (T28c): add, list, change, remove, and the
watch's own state of each (broadcaster id, push subscription, live)."""

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from clipforge.channel_rows import WatchedStreamerRow
from clipforge.models import (
    WatchedStreamer,
    WatchedStreamerCreate,
    WatchedStreamerPatch,
)


class StreamerExists(ValueError):
    """The streamer is already watched."""


class StreamerNotFound(LookupError):
    """No watched streamer has the id."""


def add_streamer(engine: Engine, create: WatchedStreamerCreate) -> WatchedStreamer:
    """Watch a Twitch login; raise StreamerExists if it is already watched.
    The watch resolves its broadcaster id at its next run."""
    row = WatchedStreamerRow(login=create.login, display_name=create.login)
    with Session(engine) as session:
        session.add(row)
        try:
            session.commit()
        except IntegrityError as exc:
            raise StreamerExists(f"{create.login} is already watched") from exc
        session.refresh(row)
        return row.to_model()


def list_streamers(engine: Engine) -> list[WatchedStreamer]:
    """Return the watched streamers, oldest first."""
    with Session(engine) as session:
        rows = session.exec(
            select(WatchedStreamerRow).order_by(col(WatchedStreamerRow.id))
        )
        return [row.to_model() for row in rows]


def find_streamer(engine: Engine, user_id: str) -> WatchedStreamer | None:
    """Return the watched streamer with this broadcaster id, if any."""
    with Session(engine) as session:
        row = session.exec(
            select(WatchedStreamerRow).where(WatchedStreamerRow.user_id == user_id)
        ).first()
        return row.to_model() if row is not None else None


def update_streamer(
    engine: Engine, streamer_id: int, patch: WatchedStreamerPatch
) -> WatchedStreamer:
    """Turn a streamer's watch on or off; raise StreamerNotFound."""
    with Session(engine) as session:
        row = _row(session, streamer_id)
        row.enabled = patch.enabled
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def remove_streamer(engine: Engine, streamer_id: int) -> None:
    """Stop watching a streamer (its alerts stay); raise StreamerNotFound."""
    with Session(engine) as session:
        session.delete(_row(session, streamer_id))
        session.commit()


def set_streamer_fields(engine: Engine, streamer_id: int, **fields: object) -> None:
    """Set fields of a streamer's row (nothing if it was removed)."""
    with Session(engine) as session:
        row = session.get(WatchedStreamerRow, streamer_id)
        if row is None:
            return
        for name, value in fields.items():
            setattr(row, name, value)
        session.add(row)
        session.commit()


def _row(session: Session, streamer_id: int) -> WatchedStreamerRow:
    row = session.get(WatchedStreamerRow, streamer_id)
    if row is None:
        raise StreamerNotFound(f"watched streamer {streamer_id} not found")
    return row
