"""The plan that the rule-based Director builds move by move (SPEC-v3 3.5).

Every move is placed where post-processing would snap it (snap.snap_target
of its anchor with the preset's snap mode, then the frame grid, its length
in frames kept and cut at the clip end) and only kept when the plan stays
valid: the preset allows the kind, no overlap or stack limit of its track
is broken (edl.track_problems), the intensity's budget holds
(budgets.budget_problems, whole-clip looks not counted), no SFX covers a
punchline word and no visual interrupt starts in a reaction hold
(pacing.broken_hold). A move that does not fit is left out with the reason why,
so rules earlier in a preset win over later ones and post-processing has
nothing left to drop. A composite move is placed whole or not at all: its
placer takes a snapshot first and restores it when a part does not fit.
A builder that is not budgeted skips the budget check (it expands a plan
whose budgets post-processing enforces).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from clipforge.models import EdlItem, EdlKind, ProEditPlan
from clipforge.proedit.budgets import IntensityBudget, budget_problems
from clipforge.proedit.edl import TRACK_OF_KIND, parse_item, track_problems
from clipforge.proedit.pacing import Span, broken_hold
from clipforge.proedit.preset_defs import Move
from clipforge.proedit.snap import (
    DEFAULT_SNAP,
    END_ANCHORED,
    EPSILON,
    PlanTiming,
    SnapMode,
    snap_target,
)


@dataclass(frozen=True)
class Snapshot:
    """The state of a PlanBuilder to restore (PlanBuilder.snapshot)."""

    items: tuple[EdlItem, ...]
    next_id: int
    left_out: int


@dataclass(frozen=True)
class LeftOut:
    """A move the Director wanted at t seconds but left out, and why."""

    move: Move
    t: float
    reason: str
    why: str


class PlanBuilder:
    """The items of a plan being built (module docstring) on template (a
    plan whose own items are ignored), keeping the reaction holds holds
    (pacing.reaction_holds)."""

    def __init__(
        self,
        template: ProEditPlan,
        timing: PlanTiming,
        budget: IntensityBudget,
        allowed: Iterable[EdlKind],
        snap_modes: Mapping[EdlKind, SnapMode] | None = None,
        holds: Sequence[Span] = (),
        budgeted: bool = True,
    ) -> None:
        self.template = template
        self.timing = timing
        self.budget = budget
        self.allowed = frozenset(allowed)
        self.snap_modes = {**DEFAULT_SNAP, **(snap_modes or {})}
        self.holds = tuple(holds)
        self.budgeted = budgeted
        self.items: list[EdlItem] = []
        self.left_out: list[LeftOut] = []
        self._next_id = 1

    def frames(self, kind: EdlKind, start: float, end: float) -> tuple[int, int] | None:
        """The frames (first, end) of a move of kind planned from start to
        end once snapped (module docstring); None if no frame is in the clip."""
        fps = self.timing.fps
        length = max(1, round((end - start) * fps))
        anchor = end if kind in END_ANCHORED else start
        frame = round(snap_target(anchor, self.snap_modes[kind], self.timing) * fps)
        first, last = (
            (frame - length, frame) if kind in END_ANCHORED else (frame, frame + length)
        )
        first, last = max(first, 0), min(last, self.timing.last_frame)
        return (first, last) if last > first else None

    def candidate(
        self,
        kind: EdlKind,
        start: float,
        end: float,
        params: dict[str, Any],
        reason: str,
    ) -> EdlItem | None:
        """The move as a snapped item with the next free id, or None when
        it has no frame in the clip. Raises EdlValidationError on bad params
        (a preset or Director bug, not a reason to leave a move out)."""
        frames = self.frames(kind, start, end)
        if frames is None:
            return None
        fps = self.timing.fps
        item = EdlItem(
            id=self._next_id,
            kind=kind,
            t_start=frames[0] / fps,
            t_end=frames[1] / fps,
            params=params,
            reason=reason,
        )
        parse_item(item)
        return item

    def problem(self, item: EdlItem) -> str | None:
        """Why item cannot join the plan (module docstring), or None."""
        if item.kind not in self.allowed:
            return f"the preset does not use {item.kind}"
        track = TRACK_OF_KIND[item.kind]
        same_track = [i for i in self.items if TRACK_OF_KIND[i.kind] == track]
        clashes = track_problems([*same_track, item])
        if clashes:
            return clashes[0]
        if self.budgeted:
            over = budget_problems(
                [*self.items, item], self.budget, self.timing.duration
            )
            if over:
                return over[0]
        if item.kind == "sfx":
            for w0, w1 in self.timing.punchlines:
                if item.t_start < w1 - EPSILON and w0 < item.t_end - EPSILON:
                    return f"it would cover the punchline word at {w0:g} s"
        hold = broken_hold(item, self.holds, self.timing)
        if hold is not None:
            return f"it would start in the reaction hold that ends at {hold[1]:g} s"
        return None

    def add(self, item: EdlItem) -> EdlItem:
        """Add item (checked by the caller) under the next free id."""
        placed = item.model_copy(update={"id": self._next_id})
        self._next_id += 1
        self.items.append(placed)
        return placed

    def fit(
        self,
        kind: EdlKind,
        start: float,
        end: float,
        params: dict[str, Any],
        reason: str,
    ) -> tuple[EdlItem | None, str]:
        """Add the move when it fits and return its item; else None and why
        it did not fit."""
        item = self.candidate(kind, start, end, params, reason)
        why = "it has no frame in the clip" if item is None else self.problem(item)
        if item is None or why is not None:
            return None, why or ""
        return self.add(item), ""

    def place(
        self,
        kind: EdlKind,
        start: float,
        end: float,
        params: dict[str, Any],
        reason: str,
        record: bool = True,
    ) -> EdlItem | None:
        """Add the move when it fits and return its item; else None, and
        with record a LeftOut that says why."""
        item, why = self.fit(kind, start, end, params, reason)
        if item is None and record:
            self.leave_out(kind, start, reason, why)
        return item

    def leave_out(self, move: Move, t: float, reason: str, why: str) -> None:
        """Record that move at t seconds was left out and why."""
        self.left_out.append(LeftOut(move, t, reason, why))

    def replace(self, items: Iterable[EdlItem]) -> None:
        """Replace the plan's items (ids kept) after a step that changed
        them as a whole (drop_moves splitting a bed)."""
        self.items = sorted(items, key=lambda i: (i.t_start, i.id))
        self._next_id = max((i.id for i in self.items), default=0) + 1

    def snapshot(self) -> Snapshot:
        """The builder's items, next id and left-out count now."""
        return Snapshot(tuple(self.items), self._next_id, len(self.left_out))

    def restore(self, snapshot: Snapshot) -> None:
        """Undo every change since snapshot (a composite that did not fit)."""
        self.items = list(snapshot.items)
        self._next_id = snapshot.next_id
        del self.left_out[snapshot.left_out :]

    def plan(self) -> ProEditPlan:
        """The template plan with the built items in time order."""
        ordered = sorted(self.items, key=lambda i: (i.t_start, i.id))
        return self.template.model_copy(update={"items": ordered})
