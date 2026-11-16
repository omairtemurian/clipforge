"""Auto Import (SPEC-v2 3.1): the watched YouTube channels, whose new videos
become projects with each channel's saved default settings.

This module keeps the channels (add, list, change, remove) and the videos
seen in their feeds; watch/youtube_watcher.AutoImporter reads the feeds and
receives the WebSub pushes (T28c).
"""

from collections.abc import Collection

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from clipforge.channel_rows import WatchedChannelRow, WatchedVideoRow
from clipforge.models import (
    WatchedChannel,
    WatchedChannelCreate,
    WatchedChannelPatch,
    WatchedVideo,
)
from clipforge.sources.youtube_feed import FeedEntry


class ChannelExists(ValueError):
    """The channel is already watched."""


class ChannelNotFound(LookupError):
    """No watched channel has the id."""


def add_channel(
    engine: Engine,
    create: WatchedChannelCreate,
    *,
    campaign_id: int | None = None,
    enabled: bool = True,
) -> WatchedChannel:
    """Watch a channel with the given defaults, for campaign campaign_id if
    given; raise ChannelExists if it is already watched. Its feed is first
    read by the next poll. An @handle must be resolved to the channel id
    first (ValueError)."""
    if create.channel.startswith("@"):
        raise ValueError(f"{create.channel} is not resolved to a channel id")
    row = WatchedChannelRow(
        channel_id=create.channel,
        settings=create.settings,
        source_rights=create.source_rights,
        credit_line=create.credit_line,
        auto_schedule_drafts=create.auto_schedule_drafts,
        enabled=enabled,
        campaign_id=campaign_id,
    )
    with Session(engine) as session:
        session.add(row)
        try:
            session.commit()
        except IntegrityError as exc:
            raise ChannelExists(f"channel {create.channel} is already watched") from exc
        session.refresh(row)
        return row.to_model()


def list_channels(engine: Engine) -> list[WatchedChannel]:
    """Return the watched channels, oldest first."""
    with Session(engine) as session:
        rows = session.exec(
            select(WatchedChannelRow).order_by(col(WatchedChannelRow.id))
        )
        return [row.to_model() for row in rows]


def find_channel(engine: Engine, channel_id: str) -> WatchedChannel | None:
    """Return the watched channel with this "UC..." id, if any."""
    with Session(engine) as session:
        row = session.exec(
            select(WatchedChannelRow).where(WatchedChannelRow.channel_id == channel_id)
        ).first()
        return row.to_model() if row is not None else None


def campaign_channels(engine: Engine, campaign_id: int) -> list[WatchedChannel]:
    """Return the channels that campaign campaign_id registered, oldest first."""
    with Session(engine) as session:
        rows = session.exec(
            select(WatchedChannelRow)
            .where(WatchedChannelRow.campaign_id == campaign_id)
            .order_by(col(WatchedChannelRow.id))
        )
        return [row.to_model() for row in rows]


def remove_campaign_channels(
    engine: Engine, campaign_id: int, keep: Collection[str] = ()
) -> None:
    """Stop watching the channels that campaign campaign_id registered, except
    those whose "UC..." id is in keep, and forget their videos."""
    for channel in campaign_channels(engine, campaign_id):
        if channel.channel_id not in keep:
            remove_channel(engine, channel.id)


def get_channel(engine: Engine, watched_channel_id: int) -> WatchedChannel:
    """Return a watched channel; raise ChannelNotFound if there is none."""
    with Session(engine) as session:
        return _row(session, watched_channel_id).to_model()


def update_channel(
    engine: Engine, watched_channel_id: int, patch: WatchedChannelPatch
) -> WatchedChannel:
    """Change the fields of a watched channel that patch sends; raise
    ChannelNotFound if there is none. The new defaults apply to the videos
    imported from now on."""
    with Session(engine) as session:
        row = _row(session, watched_channel_id)
        for name in patch.model_fields_set:
            setattr(row, name, getattr(patch, name))
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def remove_channel(engine: Engine, watched_channel_id: int) -> None:
    """Stop watching a channel and forget its videos (the projects made from
    them stay); raise ChannelNotFound if there is none."""
    with Session(engine) as session:
        session.delete(_row(session, watched_channel_id))
        session.commit()


def _row(session: Session, watched_channel_id: int) -> WatchedChannelRow:
    row = session.get(WatchedChannelRow, watched_channel_id)
    if row is None:
        raise ChannelNotFound(f"watched channel {watched_channel_id} not found")
    return row


def channel_videos(engine: Engine, watched_channel_id: int) -> list[WatchedVideo]:
    """Return the videos seen in a watched channel's feed, newest first."""
    with Session(engine) as session:
        rows = session.exec(
            select(WatchedVideoRow)
            .where(WatchedVideoRow.watched_channel_id == watched_channel_id)
            .order_by(col(WatchedVideoRow.seen_at).desc())
        )
        return [row.to_model() for row in rows]


def set_channel_fields(
    engine: Engine, watched_channel_id: int, **fields: object
) -> None:
    """Set fields of a channel's row (nothing if it was removed): the
    watch's own state (last read, errors, push subscription)."""
    with Session(engine) as session:
        row = session.get(WatchedChannelRow, watched_channel_id)
        if row is None:
            return
        for name, value in fields.items():
            setattr(row, name, value)
        session.add(row)
        session.commit()


def seen_video_ids(engine: Engine, watched_channel_id: int) -> set[str]:
    """Return the ids of the videos recorded for a watched channel."""
    with Session(engine) as session:
        ids = session.exec(
            select(WatchedVideoRow.video_id).where(
                WatchedVideoRow.watched_channel_id == watched_channel_id
            )
        )
        return set(ids)


def record_video(
    engine: Engine, watched_channel_id: int, entry: FeedEntry, project_id: int | None
) -> None:
    """Record a video seen in a channel's feed (project_id: its project,
    None if it was not imported)."""
    with Session(engine) as session:
        session.add(
            WatchedVideoRow(
                watched_channel_id=watched_channel_id,
                video_id=entry.video_id,
                title=entry.title,
                published_at=entry.published,
                project_id=project_id,
            )
        )
        session.commit()
