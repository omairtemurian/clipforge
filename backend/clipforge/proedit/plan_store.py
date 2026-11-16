"""The stored plans of a Pro Edit variant (SPEC-v3 3.1, 6): every change
keeps the plan before it, so a clip's plans are versions 1, 2, ... and the
current plan is the newest version.

save_plan stores a plan as the clip's next version with its items (the
plan's id and version are set by the database and the clip's history);
the plan it returns has them.
"""

from sqlalchemy import func
from sqlmodel import Session, col, select

from clipforge.models import EdlCreatedBy, ProEditPlan
from clipforge.proedit.rows import EdlItemRow, ProEditPlanRow


def plan_versions(session: Session, clip_id: int) -> list[ProEditPlan]:
    """Return the plans of clip clip_id, oldest version first."""
    rows = session.exec(
        select(ProEditPlanRow)
        .where(ProEditPlanRow.clip_id == clip_id)
        .order_by(col(ProEditPlanRow.version))
    ).all()
    return [_with_items(session, row) for row in rows]


def get_plan(session: Session, plan_id: int) -> ProEditPlan | None:
    """Return plan plan_id with its items, or None if there is none."""
    row = session.get(ProEditPlanRow, plan_id)
    return None if row is None else _with_items(session, row)


def current_plan(session: Session, clip_id: int) -> ProEditPlan | None:
    """Return the newest plan of clip clip_id, or None if it has none."""
    row = session.exec(
        select(ProEditPlanRow)
        .where(ProEditPlanRow.clip_id == clip_id)
        .order_by(col(ProEditPlanRow.version).desc())
        .limit(1)
    ).first()
    return None if row is None else _with_items(session, row)


def first_plan(session: Session, clip_id: int) -> ProEditPlan | None:
    """Return plan version 1 of clip clip_id, or None if it has none."""
    row = session.exec(
        select(ProEditPlanRow)
        .where(ProEditPlanRow.clip_id == clip_id)
        .where(ProEditPlanRow.version == 1)
    ).first()
    return None if row is None else _with_items(session, row)


def next_version(session: Session, clip_id: int) -> int:
    """Return the version the next plan of clip clip_id gets."""
    newest = session.exec(
        select(func.max(ProEditPlanRow.version)).where(
            ProEditPlanRow.clip_id == clip_id
        )
    ).one()
    return 1 if newest is None else int(newest) + 1


def save_plan(
    session: Session, plan: ProEditPlan, created_by: EdlCreatedBy | None = None
) -> ProEditPlan:
    """Store plan's items as the next version of its clip's plan (made by
    created_by, default the plan's own) and commit; return it with its new
    id and version."""
    row = ProEditPlanRow(
        clip_id=plan.clip_id,
        preset=plan.preset,
        intensity=plan.intensity,
        style_recipe_id=plan.style_recipe_id,
        version=next_version(session, plan.clip_id),
        rationale=plan.rationale,
        created_by=plan.created_by if created_by is None else created_by,
    )
    session.add(row)
    session.flush()
    assert row.id is not None
    for item in plan.items:
        session.add(
            EdlItemRow(
                plan_id=row.id,
                item_id=item.id,
                t_start=item.t_start,
                t_end=item.t_end,
                kind=item.kind,
                params=item.params,
                reason=item.reason,
                source=item.source,
            )
        )
    session.commit()
    session.refresh(row)
    return _with_items(session, row)


def _with_items(session: Session, row: ProEditPlanRow) -> ProEditPlan:
    items = session.exec(select(EdlItemRow).where(EdlItemRow.plan_id == row.id)).all()
    return row.to_model(items)
