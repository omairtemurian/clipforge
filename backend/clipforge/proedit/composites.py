"""The composite moves of a Pro Edit plan (SPEC-v3 3.4): a Skull Moment and
a bass drop are several items that only work together, so the budgets
count each as one unit and post-processing keeps it whole or drops it whole.

A composite is found from its items (no field marks it, so plans the LLM
wrote, the critic revised or the owner edited are judged the same way):
- skull_moment: a freeze frame with a grade change or an overlay starting
  on its frame; it takes one (the first) grade change, overlay, zoom punch,
  shake, SFX and audio effect starting on that frame, the first SFX starting when
  the freeze ends (the whoosh of the snap back to color) and the lead-in of
  a drop into it;
- bass_drop: a bass boost with an impact SFX starting on its frame, and
  the lead-in of the drop: the silence that ends on it and a riser that
  ends at most SILENCE_MAX_S before it.
Whole-clip looks (is_look) are never part of a composite.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from clipforge.models import EdlItem, EdlKind
from clipforge.proedit.audio.drop import IMPACT, RISER
from clipforge.proedit.edl_params import SILENCE_MAX_S
from clipforge.proedit.snap import EPSILON, PlanNote

Composite = Literal["skull_moment", "bass_drop"]
# Items of a composite start on the same frame: a millisecond apart at most.
SAME_FRAME_S = 1e-3
SKULL_MARKS: frozenset[EdlKind] = frozenset({"grade_change", "overlay"})
SKULL_MEMBERS: frozenset[EdlKind] = SKULL_MARKS | {
    "zoom_punch",
    "shake",
    "sfx",
    "audio_fx",
}


@dataclass(frozen=True)
class CompositeGroup:
    """A composite move: which, its moment t (the freeze's or the bass
    boost's start) and the ids of its items."""

    move: Composite
    t: float
    ids: frozenset[int]

    @property
    def label(self) -> str:
        """The move as words ("skull moment")."""
        return self.move.replace("_", " ")


@dataclass(frozen=True)
class BudgetUnit:
    """What a budget counts as one: a composite's items at its moment t, or
    a single item (move None) at its start."""

    items: tuple[EdlItem, ...]
    t: float
    move: Composite | None = None


def is_look(item: EdlItem, clip_duration: float | None) -> bool:
    """Whether item lasts the whole clip of clip_duration seconds (a
    preset's base look, e.g. its grade): no budget counts it."""
    return (
        clip_duration is not None
        and item.t_start <= EPSILON
        and item.t_end >= clip_duration - EPSILON
    )


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= SAME_FRAME_S


def _lead_in(pool: Sequence[EdlItem], t: float) -> set[int]:
    """The silence ending at t and a riser ending at most SILENCE_MAX_S
    before t."""
    found: set[int] = set()
    for item in pool:
        silence = item.kind == "silence_before_drop" and _same(item.t_end, t)
        riser = (
            item.kind == "sfx"
            and item.params.get("asset") == RISER
            and t - SILENCE_MAX_S - SAME_FRAME_S <= item.t_end <= t + SAME_FRAME_S
        )
        if silence or riser:
            found.add(item.id)
    return found


def find_composites(
    items: Iterable[EdlItem], clip_duration: float | None = None
) -> list[CompositeGroup]:
    """The composites of items (module docstring), in time order; an item
    belongs to one composite at most, Skull Moments first."""
    pool = sorted(
        (i for i in items if not is_look(i, clip_duration)),
        key=lambda i: (i.t_start, i.id),
    )
    taken: set[int] = set()
    groups: list[CompositeGroup] = []
    for freeze in [i for i in pool if i.kind == "freeze_frame"]:
        free = [i for i in pool if i.id not in taken and i.id != freeze.id]
        on_frame = [i for i in free if _same(i.t_start, freeze.t_start)]
        members = [
            m
            for kind in sorted(SKULL_MEMBERS)
            if (m := next((i for i in on_frame if i.kind == kind), None))
        ]
        if freeze.id in taken or not any(m.kind in SKULL_MARKS for m in members):
            continue
        ids = {freeze.id, *(m.id for m in members)}
        whoosh = next(
            (
                i
                for i in free
                if i.kind == "sfx"
                and i.id not in ids
                and _same(i.t_start, freeze.t_end)
            ),
            None,
        )
        ids |= {whoosh.id} if whoosh else set()
        ids |= _lead_in(free, freeze.t_start)
        taken |= ids
        groups.append(CompositeGroup("skull_moment", freeze.t_start, frozenset(ids)))
    for boost in pool:
        if boost.id in taken or boost.params.get("effect") != "bass_boost":
            continue
        free = [i for i in pool if i.id not in taken]
        impact = next(
            (
                i
                for i in free
                if i.kind == "sfx"
                and i.params.get("asset") == IMPACT
                and _same(i.t_start, boost.t_start)
            ),
            None,
        )
        if impact is None:
            continue
        ids = {boost.id, impact.id, *_lead_in(free, boost.t_start)}
        taken |= ids
        groups.append(CompositeGroup("bass_drop", boost.t_start, frozenset(ids)))
    return sorted(groups, key=lambda g: (g.t, min(g.ids)))


def budget_units(
    items: Sequence[EdlItem], clip_duration: float | None = None
) -> list[BudgetUnit]:
    """items as the budgets count them: one unit per composite, one per
    other item."""
    groups = find_composites(items, clip_duration)
    grouped = {n for g in groups for n in g.ids}
    units = [
        BudgetUnit(
            tuple(i for i in items if i.id in g.ids),
            g.t,
            g.move,
        )
        for g in groups
    ]
    units += [BudgetUnit((i,), i.t_start) for i in items if i.id not in grouped]
    return units


def member_ids(groups: Iterable[CompositeGroup]) -> frozenset[int]:
    """The ids of the items of groups."""
    return frozenset(n for g in groups for n in g.ids)


def keep_whole(
    items: Sequence[EdlItem],
    groups: Sequence[CompositeGroup],
    notes: Sequence[PlanNote],
) -> tuple[list[EdlItem], list[PlanNote]]:
    """After a step that dropped items (with notes), drop the rest of every
    composite of groups that lost an item; return the items left and a note
    per item dropped here."""
    present = {i.id for i in items}
    why = {n.item_id: n for n in notes if n.action == "dropped"}
    dropped: dict[int, PlanNote] = {}
    for group in groups:
        lost = sorted(group.ids - present)
        if not lost or not group.ids & present:
            continue
        cause = why.get(lost[0])
        what = (
            f"its {cause.kind} was dropped ({cause.reason})"
            if cause
            else "an item of it was dropped"
        )
        reason = f"part of the {group.label} at {group.t:.2f} s and {what}"
        for item in items:
            if item.id in group.ids:
                dropped[item.id] = PlanNote(
                    item.id, item.kind, "dropped", reason, item.t_start
                )
    kept = [i for i in items if i.id not in dropped]
    return kept, sorted(dropped.values(), key=lambda n: n.item_id)
