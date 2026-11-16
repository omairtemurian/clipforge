"""SQLModel rows of the autopilot (migrations 035_v2_autopilot,
036_v2_autopilot_pause and 037_v2_draft_notes); the rows of the drafts and
the feedback return the matching models of clipforge.models."""

from datetime import UTC, datetime

from sqlmodel import AutoString, Field, SQLModel

from clipforge import campaign_rows, db  # noqa: F401  (tables of the foreign keys)
from clipforge.db import PydanticJSON
from clipforge.models import (
    AutopilotSettings,
    Draft,
    DraftNote,
    DraftStatus,
    FeedbackAction,
    FeedbackEvent,
    ProEditIntensity,
    ProEditPreset,
    RejectReason,
    RuleResult,
    ScheduleRules,
)
from clipforge.watch.times import as_utc


class AutopilotSettingsRow(SQLModel, table=True):
    """A row of the autopilot_settings table: the settings of one campaign."""

    __tablename__ = "autopilot_settings"

    campaign_id: int = Field(
        primary_key=True, foreign_key="campaign.id", ondelete="CASCADE"
    )
    enabled: bool = False
    max_clips_per_source: int = 3
    slots: ScheduleRules | None = Field(
        default=None, sa_type=PydanticJSON(ScheduleRules)
    )
    max_posts_per_day: int = 3
    draft_ttl_days: int = 3
    account_ids: list[int] = Field(
        default_factory=list, sa_type=PydanticJSON(list[int])
    )
    min_clip_s: float | None = None
    max_clip_s: float | None = None
    caption_template: str | None = None
    brand_template_id: int | None = Field(
        default=None, foreign_key="brand_template.id", ondelete="SET NULL"
    )
    proedit_enabled: bool = False
    proedit_preset: ProEditPreset = Field(default="clean_pro", sa_type=AutoString)
    proedit_max_intensity: ProEditIntensity = Field(
        default="standard", sa_type=AutoString
    )

    def to_model(self) -> AutopilotSettings:
        """Return this row as validated AutopilotSettings."""
        return AutopilotSettings.model_validate(self, from_attributes=True)


class DraftRow(SQLModel, table=True):
    """A row of the draft table: one clip waiting for the owner."""

    __tablename__ = "draft"

    id: int | None = Field(default=None, primary_key=True)
    clip_id: int = Field(foreign_key="clip.id", ondelete="CASCADE", unique=True)
    campaign_id: int = Field(foreign_key="campaign.id", ondelete="CASCADE", index=True)
    status: DraftStatus = Field(default="pending", sa_type=AutoString, index=True)
    rule_results: list[RuleResult] = Field(
        default_factory=list, sa_type=PydanticJSON(list[RuleResult])
    )
    reject_reason: RejectReason | None = Field(default=None, sa_type=AutoString)
    decided_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: list[DraftNote] = Field(
        default_factory=list, sa_type=PydanticJSON(list[DraftNote])
    )

    def to_model(self) -> Draft:
        """Return this row as a validated Draft, times in UTC."""
        draft = Draft.model_validate(self, from_attributes=True)
        draft.created_at = as_utc(draft.created_at)
        if draft.decided_at is not None:
            draft.decided_at = as_utc(draft.decided_at)
        return draft


class FeedbackEventRow(SQLModel, table=True):
    """A row of the feedback_event table: one decision about a clip."""

    __tablename__ = "feedback_event"

    id: int | None = Field(default=None, primary_key=True)
    clip_id: int | None = Field(
        default=None, foreign_key="clip.id", ondelete="SET NULL"
    )
    campaign_id: int = Field(foreign_key="campaign.id", ondelete="CASCADE", index=True)
    action: FeedbackAction = Field(sa_type=AutoString)
    reason: RejectReason | None = Field(default=None, sa_type=AutoString)
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_model(self) -> FeedbackEvent:
        """Return this row as a FeedbackEvent, the time in UTC."""
        event = FeedbackEvent.model_validate(self, from_attributes=True)
        event.at = as_utc(event.at)
        return event


class AutopilotPauseRow(SQLModel, table=True):
    """The one row (id 1) of the autopilot_pause table: there while the owner
    has paused every campaign's autopilot."""

    __tablename__ = "autopilot_pause"

    id: int = Field(default=1, primary_key=True)
    paused_at: datetime
