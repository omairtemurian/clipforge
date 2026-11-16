"""The Pro Edit variants of a clip (SPEC-v3 0.13): clips of their own with
variant "pro_edit" whose parent_clip_id is the clip they were made from."""

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge.db import ClipRow
from clipforge.models import Clip


def list_variants(engine: Engine, clip_id: int) -> list[Clip]:
    """Return the Pro Edit variants of clip clip_id, oldest first."""
    with Session(engine) as session:
        rows = session.exec(
            select(ClipRow)
            .where(ClipRow.parent_clip_id == clip_id)
            .where(ClipRow.variant == "pro_edit")
            .order_by(col(ClipRow.id))
        ).all()
        return [row.to_model() for row in rows]
