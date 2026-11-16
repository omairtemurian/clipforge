"""SQLModel rows of the connected social accounts and the posts of clips
(migration 018_v2_social); to_model() returns the matching model of
clipforge.models."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import UniqueConstraint
from sqlmodel import AutoString, Field, SQLModel

from clipforge import asset_rows  # noqa: F401  (the asset table of the foreign key)
from clipforge.db import PydanticJSON
from clipforge.models import Post, PostStatus, SocialAccount, SocialPlatform


def _utc(moment: datetime | None) -> datetime | None:
    """Return moment as UTC (SQLite gives back datetimes without a zone)."""
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=UTC)


class SocialAccountRow(SQLModel, table=True):
    """A row of the social_account table; scopes and restrictions are JSON."""

    __tablename__ = "social_account"
    __table_args__ = (UniqueConstraint("platform", "external_id"),)

    id: int | None = Field(default=None, primary_key=True)
    platform: SocialPlatform = Field(sa_type=AutoString)
    external_id: str
    display_name: str = ""
    token_ref: str = Field(unique=True)
    scopes: list[str] = Field(default_factory=list, sa_type=PydanticJSON(list[str]))
    connected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    restrictions: list[str] = Field(
        default_factory=list, sa_type=PydanticJSON(list[str])
    )
    is_default: bool = False
    avatar_url: str | None = None
    always_hashtags: list[str] = Field(
        default_factory=list, sa_type=PydanticJSON(list[str])
    )

    def to_model(self) -> SocialAccount:
        """Return this row as a validated SocialAccount."""
        account = SocialAccount.model_validate(self, from_attributes=True)
        account.connected_at = _utc(account.connected_at) or account.connected_at
        return account


class PostRow(SQLModel, table=True):
    """A row of the post table; payload is stored as JSON."""

    __tablename__ = "post"

    id: int | None = Field(default=None, primary_key=True)
    clip_id: int = Field(foreign_key="clip.id", ondelete="CASCADE")
    account_id: int | None = Field(
        default=None, foreign_key="social_account.id", ondelete="SET NULL"
    )
    platform: SocialPlatform = Field(sa_type=AutoString)
    payload: dict[str, Any] = Field(
        default_factory=dict, sa_type=PydanticJSON(dict[str, Any])
    )
    thumbnail_asset_id: int | None = Field(
        default=None, foreign_key="asset.id", ondelete="SET NULL"
    )
    scheduled_at: datetime | None = None
    status: PostStatus = Field(default="draft", sa_type=AutoString)
    external_post_id: str | None = None
    url: str | None = None
    error: str | None = None
    attempts: int = 0
    attempted_at: datetime | None = None
    next_attempt_at: datetime | None = None

    def to_model(self) -> Post:
        """Return this row as a validated Post."""
        post = Post.model_validate(self, from_attributes=True)
        post.scheduled_at = _utc(post.scheduled_at)
        post.attempted_at = _utc(post.attempted_at)
        post.next_attempt_at = _utc(post.next_attempt_at)
        return post
