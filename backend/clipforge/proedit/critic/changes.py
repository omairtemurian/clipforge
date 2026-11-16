"""The EDL changes the Pro Edit critic may ask for (SPEC-v3 3.7), part of its
reply: add an item, remove an item by id, or modify an item's times or
params by id. The reply's schema only checks their shape; revise applies
each one with the plan's validation and ignores, with the reason, those
that break a rule."""

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from clipforge.models import EdlKind


class _Change(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, pattern=r"\S")


class AddChange(_Change):
    """Add an item of kind from t_start to t_end (seconds of the clip) with
    params; reason becomes the item's reason."""

    op: Literal["add"]
    kind: EdlKind
    t_start: float = Field(ge=0)
    t_end: float = Field(gt=0)
    params: dict[str, Any] = Field(default_factory=dict)


class RemoveChange(_Change):
    """Remove item item_id."""

    op: Literal["remove"]
    item_id: int = Field(ge=1)


class ModifyChange(_Change):
    """Move item item_id to t_start/t_end and/or set some of its params (the
    params not named keep their values); at least one must be given."""

    op: Literal["modify"]
    item_id: int = Field(ge=1)
    t_start: float | None = Field(default=None, ge=0)
    t_end: float | None = Field(default=None, gt=0)
    params: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _changes_something(self) -> Self:
        if self.t_start is None and self.t_end is None and not self.params:
            raise ValueError("a modify change needs t_start, t_end or params")
        return self


CriticChange = Annotated[
    AddChange | RemoveChange | ModifyChange, Field(discriminator="op")
]
