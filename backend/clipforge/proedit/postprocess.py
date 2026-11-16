"""The deterministic post-processing of a Pro Edit plan after any planner
(SPEC-v3 3.1, 3.5): snapping, punchline protection, the reaction holds
after punchlines (pacing.hold_reactions), then the intensity budgets. A
composite (composites.py: a Skull Moment, a bass drop) is kept whole or
dropped whole through every step. The result says what was moved or
dropped and why, and where the plan still lacks a pattern interrupt."""

from collections.abc import Mapping
from dataclasses import dataclass

from clipforge.models import EdlKind, ProEditPlan
from clipforge.proedit.budgets import (
    PresetBudget,
    effective_budget,
    enforce_budgets,
    interrupt_gaps,
)
from clipforge.proedit.composites import find_composites, keep_whole, member_ids
from clipforge.proedit.pacing import hold_reactions
from clipforge.proedit.snap import (
    PlanNote,
    PlanTiming,
    SnapMode,
    protect_punchlines,
    snap_items,
)


@dataclass(frozen=True)
class PostProcessed:
    """The post-processed plan, a note per moved or dropped item, and the
    spans with no pattern interrupt longer than the intensity's target."""

    plan: ProEditPlan
    notes: list[PlanNote]
    interrupt_gaps: list[tuple[float, float]]


def postprocess_plan(
    plan: ProEditPlan,
    timing: PlanTiming,
    preset_budget: PresetBudget | None = None,
    snap_modes: Mapping[EdlKind, SnapMode] | None = None,
) -> PostProcessed:
    """Snap the plan's items to frames, words and beats, move or drop the
    SFX over punchline words and the visual interrupts in reaction holds,
    drop the rest of any composite that lost an item, and drop the
    lowest-priority items (or composites) over the
    budget of the plan's intensity (lowered by the preset's); items over
    the whole clip are base looks that no budget counts."""
    budget = effective_budget(plan.intensity, preset_budget)
    groups = find_composites(plan.items, timing.duration)
    fixed = member_ids(groups)
    items, notes = snap_items(plan.items, timing, snap_modes, fixed)
    items, punchline_notes = protect_punchlines(items, timing, fixed)
    notes += punchline_notes
    items, hold_notes = hold_reactions(items, timing, plan.intensity, fixed)
    notes += hold_notes
    items, whole_notes = keep_whole(items, groups, notes)
    items, budget_notes = enforce_budgets(items, budget, timing.duration)
    return PostProcessed(
        plan=plan.model_copy(update={"items": items}),
        notes=[*notes, *whole_notes, *budget_notes],
        interrupt_gaps=interrupt_gaps(items, timing.duration, budget),
    )
