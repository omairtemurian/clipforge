"""The retention moves of a Pro Edit plan (SPEC-v3 3.3 retention).

Pattern interrupts: at pro and extreme (budgets.BUDGETS interrupt_s, 2-4 s)
every span longer than the intensity's longest gap with no interrupt
starting in it (budgets.interrupt_gaps) gets one: the preset's interrupt
kinds in turn (zoom changes, crop/angle changes, B-roll overlays, caption
emphasis, SFX), from the gap's shortest to its longest spacing after the
span's start, at a beat, else a word start, else on an INTERRUPT_GRID_S
grid. The rule-based Director fills its plan (fill_interrupts); an LLM
plan is filled the same way after its post-processing (fill_plan).

Loop-friendly ending (the owner's option or a style recipe that loops):
a loop transition over the clip's last LOOP_S seconds, ending on its last
frame (loop_ending_item); the renderer blends the picture into the first
frame and the sound into the opening sound (render/loop_end.py). It wins
over the auto moves of its track it overlaps (add_loop_ending).
"""

from collections.abc import Sequence

from clipforge.models import EdlItem, ProEditPlan
from clipforge.proedit.budgets import IntensityBudget, interrupt_gaps
from clipforge.proedit.composites import is_look
from clipforge.proedit.director_build import PlanBuilder
from clipforge.proedit.director_moments import Moment
from clipforge.proedit.director_moves import place_kind
from clipforge.proedit.edl import excludes, is_loop_ending
from clipforge.proedit.pacing import Span
from clipforge.proedit.preset_defs import PresetDef
from clipforge.proedit.snap import EPSILON, PlanNote, PlanTiming

INTERRUPT_GRID_S = 0.5
LOOP_S = 0.3
LOOP_REASON = "loop-friendly ending: the last frames blend into the first"


def interrupt_times(builder: PlanBuilder, start: float, end: float) -> list[float]:
    """Return the times to try for an interrupt from start to end: the
    beats and word starts in it, then the INTERRUPT_GRID_S grid."""
    timing = builder.timing
    inside = [t for t in (*timing.beats, *timing.word_starts) if start <= t <= end]
    grid = []
    t = start
    while t <= end + EPSILON:
        grid.append(t)
        t += INTERRUPT_GRID_S
    return [*dict.fromkeys([*inside, *grid])]


def fill_interrupts(builder: PlanBuilder, preset: PresetDef) -> list[EdlItem]:
    """Fill each span longer than the intensity's gap with an interrupt
    starting at most that gap after its start (module docstring); return
    the interrupts added. A span no interrupt fits is left out with why."""
    target = builder.budget.interrupt_s
    added: list[EdlItem] = []
    if target is None or not preset.interrupts:
        return added
    low, high = target
    duration = builder.timing.duration
    tried: set[float] = set()
    turn = 0
    while True:
        gaps = interrupt_gaps(builder.items, duration, builder.budget)
        open_gaps = [(a, b) for a, b in gaps if a not in tried]
        if not open_gaps:
            return added
        a, b = open_gaps[0]
        tried.add(a)
        placed = None
        for t in interrupt_times(builder, a + low, min(a + high, b)):
            for k in range(len(preset.interrupts)):
                kind = preset.interrupts[(turn + k) % len(preset.interrupts)]
                moment = Moment("interrupt", t, t, f"a pattern interrupt at {t:.2f} s")
                placed = place_kind(builder, kind, moment, preset, None, record=False)
                if placed:
                    turn += k + 1
                    break
            if placed:
                added.append(placed)
                break
        if not placed:
            why = f"no interrupt fits from {a + low:.2f} to {a + high:.2f} s"
            builder.leave_out(preset.interrupts[0], a + high, "pattern interrupt", why)


def fill_plan(
    plan: ProEditPlan,
    timing: PlanTiming,
    budget: IntensityBudget,
    preset: PresetDef,
    holds: Sequence[Span] = (),
) -> tuple[ProEditPlan, list[EdlItem]]:
    """Return plan (post-processed) with its interrupt gaps filled
    (fill_interrupts, keeping the reaction holds holds) and the items
    added."""
    builder = PlanBuilder(plan, timing, budget, preset.kinds, preset.snap, holds)
    builder.replace(plan.items)
    added = fill_interrupts(builder, preset)
    return builder.plan(), added


def loop_ending_item(timing: PlanTiming, item_id: int) -> EdlItem | None:
    """Return the loop ending (module docstring) of a clip of timing as
    item item_id, None when the clip is not longer than it."""
    last = timing.last_frame
    first = last - round(LOOP_S * timing.fps)
    if first <= 0:
        return None
    return EdlItem(
        id=item_id,
        kind="transition",
        t_start=first / timing.fps,
        t_end=last / timing.fps,
        params={"type": "loop", "whoosh": False},
        reason=LOOP_REASON,
    )


def add_loop_ending(
    items: Sequence[EdlItem], timing: PlanTiming
) -> tuple[list[EdlItem], list[PlanNote]]:
    """Return items with a loop ending (unless they have one or the clip
    is too short), the auto moves it overlaps on its track dropped, and a
    note per item dropped. When a manual item is in its way, the items are
    returned as they are."""
    if any(is_loop_ending(i) for i in items):
        return list(items), []
    loop = loop_ending_item(timing, max((i.id for i in items), default=0) + 1)
    if loop is None:
        return list(items), []
    clashing = [
        i
        for i in items
        if excludes(i.kind, loop.kind)
        and not is_look(i, timing.duration)
        and i.t_start < loop.t_end - EPSILON
        and loop.t_start < i.t_end - EPSILON
    ]
    if any(i.source == "manual" for i in clashing):
        return list(items), []
    gone = {i.id for i in clashing}
    kept = [i for i in items if i.id not in gone]
    notes = [
        PlanNote(
            i.id, i.kind, "dropped", "it overlapped the loop-friendly ending", i.t_start
        )
        for i in clashing
    ]
    return sorted([*kept, loop], key=lambda i: (i.t_start, i.id)), notes
