"""SQLModel rows of Pro Edit (migrations 039_proedit, 040_proedit_runs):
the plans and their edit decisions, the runs and the style recipes with
their references. The rows return the matching models of clipforge.models."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import UniqueConstraint
from sqlmodel import AutoString, Field, SQLModel

from clipforge import db  # noqa: F401  (the clip table of the foreign keys)
from clipforge.db import PydanticJSON
from clipforge.models import (
    CriticRound,
    EdlCreatedBy,
    EdlItem,
    EdlKind,
    EdlSource,
    ProEditIntensity,
    ProEditOptions,
    ProEditPlan,
    ProEditPreset,
    ProEditRun,
    ProEditRunMode,
    ProEditRunStatus,
    StyleRecipe,
    StyleReference,
)
from clipforge.watch.times import as_utc


class StyleRecipeRow(SQLModel, table=True):
    """A row of the style_recipe table; features are stored as JSON."""

    __tablename__ = "style_recipe"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    features: dict[str, Any] = Field(
        default_factory=dict, sa_type=PydanticJSON(dict[str, Any])
    )
    reference_count: int = 0
    created_at: datetime

    def to_model(self) -> StyleRecipe:
        """Return this row as a validated StyleRecipe, its time in UTC."""
        recipe = StyleRecipe.model_validate(self, from_attributes=True)
        recipe.created_at = as_utc(recipe.created_at)
        return recipe


class StyleReferenceRow(SQLModel, table=True):
    """A row of the style_reference table."""

    __tablename__ = "style_reference"

    id: int | None = Field(default=None, primary_key=True)
    recipe_id: int = Field(
        foreign_key="style_recipe.id", ondelete="CASCADE", index=True
    )
    url: str
    analyzed_at: datetime | None = None
    deleted_at: datetime | None = None
    rights_confirmed_at: datetime

    def to_model(self) -> StyleReference:
        """Return this row as a validated StyleReference, its times in UTC."""
        reference = StyleReference.model_validate(self, from_attributes=True)
        reference.rights_confirmed_at = as_utc(reference.rights_confirmed_at)
        if reference.analyzed_at is not None:
            reference.analyzed_at = as_utc(reference.analyzed_at)
        if reference.deleted_at is not None:
            reference.deleted_at = as_utc(reference.deleted_at)
        return reference


class ProEditPlanRow(SQLModel, table=True):
    """A row of the pro_edit_plan table: one version of a clip's plan, without
    its edit decisions (EdlItemRow)."""

    __tablename__ = "pro_edit_plan"
    __table_args__ = (UniqueConstraint("clip_id", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    clip_id: int = Field(foreign_key="clip.id", ondelete="CASCADE", index=True)
    preset: ProEditPreset = Field(sa_type=AutoString)
    intensity: ProEditIntensity = Field(sa_type=AutoString)
    style_recipe_id: int | None = Field(
        default=None, foreign_key="style_recipe.id", ondelete="SET NULL"
    )
    version: int
    rationale: str = ""
    created_by: EdlCreatedBy = Field(sa_type=AutoString)

    def to_model(self, items: Iterable["EdlItemRow"] = ()) -> ProEditPlan:
        """Return this row as a validated ProEditPlan with items, in item
        order."""
        return ProEditPlan(
            **self.model_dump(),
            items=[item.to_model() for item in sorted(items, key=_item_number)],
        )


class EdlItemRow(SQLModel, table=True):
    """A row of the edl_item table: edit decision item_id of plan plan_id;
    params are stored as JSON."""

    __tablename__ = "edl_item"

    plan_id: int = Field(
        primary_key=True, foreign_key="pro_edit_plan.id", ondelete="CASCADE"
    )
    item_id: int = Field(primary_key=True)
    t_start: float
    t_end: float
    kind: EdlKind = Field(sa_type=AutoString)
    params: dict[str, Any] = Field(
        default_factory=dict, sa_type=PydanticJSON(dict[str, Any])
    )
    reason: str
    source: EdlSource = Field(default="auto", sa_type=AutoString)

    def to_model(self) -> EdlItem:
        """Return this row as a validated EdlItem."""
        return EdlItem(
            id=self.item_id,
            t_start=self.t_start,
            t_end=self.t_end,
            kind=self.kind,
            params=self.params,
            reason=self.reason,
            source=self.source,
        )


def _item_number(item: EdlItemRow) -> int:
    return item.item_id


class ProEditRunRow(SQLModel, table=True):
    """A row of the pro_edit_run table; the critic's scores are stored as
    JSON."""

    __tablename__ = "pro_edit_run"

    id: int | None = Field(default=None, primary_key=True)
    clip_id: int = Field(foreign_key="clip.id", ondelete="CASCADE", index=True)
    plan_id: int | None = Field(
        default=None, foreign_key="pro_edit_plan.id", ondelete="SET NULL", index=True
    )
    status: ProEditRunStatus = Field(default="queued", sa_type=AutoString)
    rounds: int = 0
    critic_scores: list[CriticRound] = Field(
        default_factory=list, sa_type=PydanticJSON(list[CriticRound])
    )
    cost_estimate: float | None = None
    cost_actual: float | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    job_id: int | None = Field(
        default=None, foreign_key="job.id", ondelete="SET NULL", index=True
    )
    mode: ProEditRunMode = Field(default="start", sa_type=AutoString)
    options: ProEditOptions | None = Field(
        default=None, sa_type=PydanticJSON(ProEditOptions)
    )
    notes: list[str] = Field(default_factory=list, sa_type=PydanticJSON(list[str]))

    def to_model(self) -> ProEditRun:
        """Return this row as a validated ProEditRun, its times in UTC."""
        run = ProEditRun.model_validate(self, from_attributes=True)
        if run.started_at is not None:
            run.started_at = as_utc(run.started_at)
        if run.finished_at is not None:
            run.finished_at = as_utc(run.finished_at)
        return run
