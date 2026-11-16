"""SQLModel rows of the asset library and the usage records (migrations
005_v2_assets_rights and 039_proedit); to_model() returns the matching model of
clipforge.models."""

from datetime import UTC, datetime

from sqlmodel import AutoString, Field, SQLModel

from clipforge.db import PydanticJSON
from clipforge.models import Asset, AssetKind, UsageRecord


class AssetRow(SQLModel, table=True):
    """A row of the asset table; tags are stored as JSON."""

    __tablename__ = "asset"

    id: int | None = Field(default=None, primary_key=True)
    kind: AssetKind = Field(sa_type=AutoString)
    path: str
    license: str
    attribution: str = ""
    source_url: str | None = None
    tags: list[str] = Field(default_factory=list, sa_type=PydanticJSON(list[str]))
    bpm: float | None = None
    key: str | None = None
    loudness_lufs: float | None = None
    energy_curve: list[float] | None = Field(
        default=None, sa_type=PydanticJSON(list[float])
    )
    category: str | None = None
    mood: str | None = None
    downloaded_at: datetime | None = None

    def to_model(self) -> Asset:
        """Return this row as a validated Asset."""
        return Asset.model_validate(self, from_attributes=True)


class UsageRecordRow(SQLModel, table=True):
    """A row of the usage_record table; project_id is set NULL when the
    project is deleted."""

    __tablename__ = "usage_record"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int | None = Field(
        default=None, foreign_key="project.id", ondelete="SET NULL", index=True
    )
    kind: str
    units: float
    cost_usd: float | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)

    def to_model(self) -> UsageRecord:
        """Return this row as a validated UsageRecord."""
        return UsageRecord.model_validate(self, from_attributes=True)
