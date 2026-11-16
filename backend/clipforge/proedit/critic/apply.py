"""A critic round's revision of a Pro Edit plan (SPEC-v3 3.7): the critic's
EDL changes applied by code, with the plan's validation.

1. The changes are applied one at a time, in the reply's order. A change is
   ignored, with the problem, when it names an item the plan does not hold,
   touches an item the user placed (source "manual"), adds a kind the
   preset does not use, or leaves a problem the plan did not have before:
   invalid params, times outside the clip, overlaps per track, too many
   stacked items (edl.plan_problems) or an asset missing from the catalog.
   An added item gets the next free id and the change's reason; a modify
   keeps the item's params it does not name.
2. When a change was applied, the items become the next version of the
   plan (created_by critic_revision) and are post-processed like the
   Director's (snapping, punchline protection, reaction holds, budgets,
   whooshes: director_llm.finish_plan; no new pattern interrupts, so the
   moves the critic removed stay removed). A revision that still breaks a rule is
   dropped whole: its changes are reported as ignored. An applied change
   whose item post-processing dropped (over the budget) is reported as
   ignored with that reason.
3. "What changed" is the difference between the plan and its revision by
   item id (added, removed, modified), each with the critic's reason or
   what post-processing did. No difference: no revision.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from clipforge.models import (
    CriticChangeOp,
    EdlItem,
    IgnoredChange,
    PlanChange,
    ProEditPlan,
)
from clipforge.pipeline.curate_prompt import describe_errors
from clipforge.proedit.critic.changes import (
    AddChange,
    CriticChange,
    ModifyChange,
    RemoveChange,
)
from clipforge.proedit.director_catalog import catalog_problems
from clipforge.proedit.director_llm import finish_plan
from clipforge.proedit.director_prompt import DirectorRequest
from clipforge.proedit.edl import plan_problems

CREATED_BY = "critic_revision"
BY_POST_PROCESSING = "changed by post-processing (snapping, budgets, whooshes)"
UNDONE = "post-processing undid every change"


@dataclass(frozen=True)
class Revision:
    """The revised plan (None: nothing changed), what changed, the changes
    left out and why, and notes on what post-processing did."""

    plan: ProEditPlan | None
    changes: list[PlanChange]
    ignored: list[IgnoredChange]
    notes: list[str]


@dataclass(frozen=True)
class Applied:
    """The items after the applied changes, those changes with the id of
    the item each touched, the critic's reason per item id, and the changes
    left out."""

    items: list[EdlItem]
    changes: list[tuple[CriticChange, int]]
    reasons: dict[int, str]
    ignored: list[IgnoredChange]


def _ignored(change: CriticChange, problem: str) -> IgnoredChange:
    return IgnoredChange(
        op=change.op,
        item_id=None if isinstance(change, AddChange) else change.item_id,
        kind=change.kind if isinstance(change, AddChange) else None,
        reason=change.reason,
        problem=problem,
    )


def _changed_item(
    change: AddChange | ModifyChange, items: Sequence[EdlItem], next_id: int
) -> EdlItem:
    """Return the item an add or modify change makes; raise ValidationError
    when it is not a valid item."""
    if isinstance(change, AddChange):
        return EdlItem.model_validate(
            {**change.model_dump(exclude={"op"}), "id": next_id, "source": "auto"}
        )
    old = next(item for item in items if item.id == change.item_id)
    update = change.model_dump(include={"t_start", "t_end"}, exclude_none=True)
    params = {**old.params, **(change.params or {})}
    return EdlItem.model_validate({**old.model_dump(), **update, "params": params})


def _target_problem(change: CriticChange, items: Sequence[EdlItem]) -> str | None:
    """Why a remove or modify change cannot touch its item (None: it can)."""
    if isinstance(change, AddChange):
        return None
    item = next((i for i in items if i.id == change.item_id), None)
    if item is None:
        return f"item {change.item_id} is not in the plan"
    if item.source == "manual":
        return f"item {item.id} ({item.kind}) was placed by the user"
    return None


def _apply_one(
    change: CriticChange,
    plan: ProEditPlan,
    request: DirectorRequest,
    next_id: int,
) -> tuple[list[EdlItem] | None, str | None]:
    """Return the items after change, or None and why it is ignored."""
    problem = _target_problem(change, plan.items)
    if problem is not None:
        return None, problem
    if isinstance(change, RemoveChange):
        return [i for i in plan.items if i.id != change.item_id], None
    if isinstance(change, AddChange) and change.kind not in request.preset.kinds:
        return None, f"the {request.preset.name} preset does not use {change.kind}"
    try:
        item = _changed_item(change, plan.items, next_id)
    except ValidationError as error:
        return None, describe_errors(error).replace("\n", "; ").replace("- ", "")
    items = [item if i.id == item.id else i for i in plan.items]
    if isinstance(change, AddChange):
        items.append(item)
    duration = request.signals.duration
    before = set(plan_problems(plan, duration))
    after = plan_problems(plan.model_copy(update={"items": items}), duration)
    problems = [p for p in after if p not in before]
    if isinstance(change, AddChange) or "asset" in (change.params or {}):
        problems += catalog_problems([item], request.catalog)
    return (None, "; ".join(problems)) if problems else (items, None)


def apply_changes(
    plan: ProEditPlan, changes: Sequence[CriticChange], request: DirectorRequest
) -> Applied:
    """Apply changes to plan's items one at a time (step 1)."""
    current = plan
    done: list[tuple[CriticChange, int]] = []
    reasons: dict[int, str] = {}
    ignored: list[IgnoredChange] = []
    for change in changes:
        next_id = max((i.id for i in current.items), default=0) + 1
        items, problem = _apply_one(change, current, request, next_id)
        if items is None:
            ignored.append(_ignored(change, problem or "invalid change"))
            continue
        touched = next_id if isinstance(change, AddChange) else change.item_id
        reasons[touched] = change.reason
        done.append((change, touched))
        current = current.model_copy(update={"items": items})
    return Applied(current.items, done, reasons, ignored)


def plan_diff(
    before: Sequence[EdlItem], after: Sequence[EdlItem], reasons: dict[int, str]
) -> list[PlanChange]:
    """Return what changed from before to after by item id (step 3); reasons
    gives the why per item id (else the added item's own reason, or that
    post-processing changed it)."""
    old = {item.id: item for item in before}
    new = {item.id: item for item in after}
    diff: list[PlanChange] = []
    for item_id in sorted(old.keys() | new.keys()):
        was, now = old.get(item_id), new.get(item_id)
        if was == now:
            continue
        op: CriticChangeOp = (
            "add" if was is None else "remove" if now is None else "modify"
        )
        fallback = now.reason if was is None and now is not None else BY_POST_PROCESSING
        diff.append(
            PlanChange(
                op=op,
                item_id=item_id,
                before=was,
                after=now,
                reason=reasons.get(item_id, fallback),
            )
        )
    return diff


def revise_plan(
    plan: ProEditPlan, changes: Sequence[CriticChange], request: DirectorRequest
) -> Revision:
    """Return the revision of plan by the critic's changes (module
    docstring) for the clip, preset, intensity, music and catalog of
    request."""
    applied = apply_changes(plan, changes, request)
    if not applied.changes:
        return Revision(None, [], applied.ignored, [])
    revised = ProEditPlan.model_validate(
        {
            **plan.model_dump(exclude={"items"}),
            "items": sorted(applied.items, key=lambda i: (i.t_start, i.id)),
            "version": plan.version + 1,
            "created_by": CREATED_BY,
        }
    )
    final, notes, problems = finish_plan(revised, request, interrupts=False)
    post = {n.item_id: f"{n.action} by post-processing: {n.reason}" for n in notes}
    dropped_ids = {n.item_id for n in notes if n.action == "dropped"}
    reasons = post | applied.reasons | {i: post[i] for i in dropped_ids}
    note_texts = [f"item {n.item_id} ({n.kind}) {n.action}: {n.reason}" for n in notes]
    if problems:
        why = "the revision breaks rules after post-processing: " + "; ".join(problems)
        lost = [_ignored(c, why) for c, _ in applied.changes]
        return Revision(None, [], [*applied.ignored, *lost], [why])
    kept = {i.id for i in final.items}
    dropped = [
        _ignored(c, post.get(item_id, BY_POST_PROCESSING))
        for c, item_id in applied.changes
        if not isinstance(c, RemoveChange) and item_id not in kept
    ]
    ignored = [*applied.ignored, *dropped]
    diff = plan_diff(plan.items, final.items, reasons)
    if not diff:
        return Revision(None, [], ignored, [*note_texts, UNDONE])
    return Revision(final, diff, ignored, note_texts)
