"""SQLModel row of the clipping campaigns (migrations 015_v2_campaigns and
016_v2_campaign_preset); to_model() returns the matching model of
clipforge.models."""

from datetime import UTC, date, datetime

from sqlmodel import AutoString, Field, SQLModel

from clipforge import asset_rows  # noqa: F401  (the asset table of the foreign key)
from clipforge.db import PydanticJSON
from clipforge.models import (
    Campaign,
    CampaignBadge,
    CampaignBoard,
    CampaignPlatform,
    CampaignStatus,
    HeavyEditsAllowed,
)


class CampaignRow(SQLModel, table=True):
    """A row of the campaign table; the lists are stored as JSON."""

    __tablename__ = "campaign"

    id: int | None = Field(default=None, primary_key=True)
    permission_screenshot_asset_id: int | None = Field(
        default=None, foreign_key="asset.id", ondelete="SET NULL"
    )
    permission_checked_at: datetime | None = None
    name: str
    creator_name: str = ""
    source_channel_urls: list[str] = Field(
        default_factory=list, sa_type=PydanticJSON(list[str])
    )
    platform_board: CampaignBoard = Field(default="other", sa_type=AutoString)
    campaign_url: str | None = None
    permission_source_url: str | None = None
    badge: CampaignBadge = Field(default="open", sa_type=AutoString)
    rate_per_1k_usd: float | None = None
    budget_note: str = ""
    allowed_platforms: list[CampaignPlatform] = Field(
        default_factory=list, sa_type=PydanticJSON(list[CampaignPlatform])
    )
    required_hashtags: list[str] = Field(
        default_factory=list, sa_type=PydanticJSON(list[str])
    )
    required_credit_line: str = ""
    required_tags_mentions: list[str] = Field(
        default_factory=list, sa_type=PydanticJSON(list[str])
    )
    min_duration_s: float | None = None
    max_duration_s: float | None = None
    banned_content_notes: str = ""
    monetization_allowed_elsewhere: bool | None = None
    submission_instructions: str = ""
    status: CampaignStatus = Field(default="active", sa_type=AutoString)
    notes: str = ""
    end_date: date | None = None
    caption_template: str | None = None
    allow_heavy_edits: HeavyEditsAllowed = Field(default="unknown", sa_type=AutoString)

    def to_model(self) -> Campaign:
        """Return this row as a validated Campaign; SQLite stores the date of
        the permission without a zone, so it is read back as UTC."""
        campaign = Campaign.model_validate(self, from_attributes=True)
        checked = campaign.permission_checked_at
        if checked is not None and checked.tzinfo is None:
            campaign.permission_checked_at = checked.replace(tzinfo=UTC)
        return campaign
