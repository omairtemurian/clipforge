"""SQLModel rows of the campaign accounts and the submission tracker
(migration 034_v2_submissions); SubmissionRow.to_model() returns the
matching model of clipforge.models."""

from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import AutoString, Field, SQLModel

from clipforge import campaign_rows, social_rows  # noqa: F401  (foreign keys)
from clipforge.models import Submission, SubmissionStatus
from clipforge.watch.times import as_utc


class CampaignAccountRow(SQLModel, table=True):
    """A row of the campaign_account table: an account a campaign runs on."""

    __tablename__ = "campaign_account"
    __table_args__ = (UniqueConstraint("campaign_id", "account_id"),)

    id: int | None = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", ondelete="CASCADE")
    account_id: int = Field(
        foreign_key="social_account.id", ondelete="CASCADE", index=True
    )


class SubmissionRow(SQLModel, table=True):
    """A row of the submission table."""

    __tablename__ = "submission"

    id: int | None = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="post.id", ondelete="CASCADE", unique=True)
    campaign_id: int | None = Field(
        default=None, foreign_key="campaign.id", ondelete="SET NULL", index=True
    )
    submitted_at: datetime | None = None
    status: SubmissionStatus = Field(default="not_submitted", sa_type=AutoString)
    approved_views: int | None = None
    payout_usd: float | None = None
    notes: str = ""
    answered_at: datetime | None = None

    def to_model(self) -> Submission:
        """Return this row as a validated Submission; SQLite stores the dates
        without a zone, so they are read back as UTC."""
        submission = Submission.model_validate(self, from_attributes=True)
        if submission.submitted_at is not None:
            submission.submitted_at = as_utc(submission.submitted_at)
        if submission.answered_at is not None:
            submission.answered_at = as_utc(submission.answered_at)
        return submission
