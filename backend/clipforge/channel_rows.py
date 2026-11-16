"""SQLModel rows of the watch: Auto Import's watched channels and the videos
seen in their feeds (migration 013_v2_channels), the channels' WebSub state,
the watched Twitch streamers and the watch's alerts (014_v2_watch);
to_model() returns the matching model of clipforge.models."""

from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import AutoString, Field, SQLModel

from clipforge.db import PydanticJSON
from clipforge.models import (
    DetectedVia,
    ProcessingSettings,
    PushState,
    SourceRights,
    WatchedChannel,
    WatchedStreamer,
    WatchedVideo,
    WatchEvent,
    WatchEventKind,
    WatchPlatform,
)


class WatchedChannelRow(SQLModel, table=True):
    """A row of the watched_channel table; settings are stored as JSON."""

    __tablename__ = "watched_channel"

    id: int | None = Field(default=None, primary_key=True)
    channel_id: str = Field(unique=True)
    title: str = ""
    settings: ProcessingSettings = Field(sa_type=PydanticJSON(ProcessingSettings))
    source_rights: SourceRights | None = Field(default=None, sa_type=AutoString)
    credit_line: str = ""
    auto_schedule_drafts: bool = False
    enabled: bool = True
    last_checked_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    push_state: PushState = Field(default="off", sa_type=AutoString)
    push_lease_expires_at: datetime | None = None
    push_requested_at: datetime | None = None
    push_error: str | None = None
    campaign_id: int | None = None

    def to_model(self) -> WatchedChannel:
        """Return this row as a validated WatchedChannel."""
        return WatchedChannel.model_validate(self, from_attributes=True)


class WatchedVideoRow(SQLModel, table=True):
    """A row of the watched_video table: one video id seen in one channel's
    feed; deleted with its channel."""

    __tablename__ = "watched_video"

    watched_channel_id: int = Field(
        foreign_key="watched_channel.id", ondelete="CASCADE", primary_key=True
    )
    video_id: str = Field(primary_key=True)
    title: str = ""
    published_at: datetime | None = None
    project_id: int | None = None
    seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_model(self) -> WatchedVideo:
        """Return this row as a validated WatchedVideo."""
        return WatchedVideo.model_validate(self, from_attributes=True)


class WatchedStreamerRow(SQLModel, table=True):
    """A row of the watched_streamer table: one watched Twitch login."""

    __tablename__ = "watched_streamer"

    id: int | None = Field(default=None, primary_key=True)
    login: str = Field(unique=True)
    user_id: str | None = None
    display_name: str = ""
    enabled: bool = True
    push_state: PushState = Field(default="off", sa_type=AutoString)
    push_requested_at: datetime | None = None
    push_error: str | None = None
    subscription_id: str | None = None
    live_since: datetime | None = None
    last_live_at: datetime | None = None
    last_checked_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_model(self) -> WatchedStreamer:
        """Return this row as a validated WatchedStreamer."""
        return WatchedStreamer.model_validate(self, from_attributes=True)


class WatchEventRow(SQLModel, table=True):
    """A row of the watch_event table: one alert of the watch."""

    __tablename__ = "watch_event"
    __table_args__ = (UniqueConstraint("platform", "kind", "external_id"),)

    id: int | None = Field(default=None, primary_key=True)
    platform: WatchPlatform = Field(sa_type=AutoString)
    kind: WatchEventKind = Field(sa_type=AutoString)
    external_id: str
    source_name: str = ""
    title: str = ""
    url: str = ""
    project_id: int | None = None
    published_at: datetime | None = None
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    via: DetectedVia = Field(sa_type=AutoString)

    def to_model(self) -> WatchEvent:
        """Return this row as a validated WatchEvent."""
        return WatchEvent.model_validate(self, from_attributes=True)
