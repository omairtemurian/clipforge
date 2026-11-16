"""The composite moves of an LLM Director plan, placed by the rule-based
Director's code (SPEC-v3 3.4, 3.5).

The reply asks for a composite with a moment (director_prompt.DirectorMoment),
which reply_plan turns into its anchor item: a freeze frame for a Skull
Moment, a bass boost for a bass drop. A plan may also hold a composite the
LLM wrote item by item, often incomplete (a freeze and a boom, no skull).
Before post-processing, expand_composites rebuilds every such anchor that
is not already a whole composite (composites.find_composites) with the
rule-based Director's placers (director_skull.place_skull,
director_moves.bass_drop): the auto items it would clash with are replaced
(each with a note) and the composite is placed whole; when it still does
not fit, the plan is kept as it was and post-processing judges it.
"""

import logging
import math
from collections.abc import Sequence
from typing import Any

from clipforge.models import EdlItem, EdlKind, ProEditPlan
from clipforge.proedit.audio.drop import BASS_DROP_AMOUNT, BASS_DROP_S
from clipforge.proedit.budgets import EFFECT_KINDS, IntensityBudget
from clipforge.proedit.composites import (
    SAME_FRAME_S,
    SKULL_MARKS,
    SKULL_MEMBERS,
    find_composites,
    is_look,
)
from clipforge.proedit.director_build import PlanBuilder
from clipforge.proedit.director_moments import Moment
from clipforge.proedit.director_moves import bass_drop
from clipforge.proedit.director_prompt import DirectorMoment, DirectorRequest
from clipforge.proedit.director_skull import (
    HOLD_MAX_S,
    HOLD_MIN_S,
    SNAP_BACK_WHOOSH_S,
    place_skull,
)
from clipforge.proedit.edl import TRACK_OF_KIND, is_loop_ending
from clipforge.proedit.preset_defs import PresetDef
from clipforge.proedit.snap import EPSILON, PlanNote, PlanTiming

logger = logging.getLogger(__name__)

WHOLE_SKULL: frozenset[EdlKind] = SKULL_MEMBERS | {"freeze_frame"}
WHOLE_DROP: frozenset[EdlKind] = frozenset({"sfx", "audio_fx"})
_VISUAL: frozenset[EdlKind] = EFFECT_KINDS | {
    k for k, track in TRACK_OF_KIND.items() if track == "zoom"
}


def moment_problems(
    moments: Sequence[DirectorMoment], request: DirectorRequest
) -> list[str]:
    """Why the reply's moments cannot be placed (empty: they can)."""
    problems = []
    last = request.signals.duration - 1 / request.signals.fps
    for n, moment in enumerate(moments, start=1):
        if moment.t > last:
            problems.append(f"moment {n} ({moment.move}): t is past the clip end")
        if moment.move == "skull_moment" and request.preset.skull is None:
            problems.append(
                f"moment {n}: the {request.preset.name} preset has no Skull Moment"
            )
    return problems


def moment_anchors(
    moments: Sequence[DirectorMoment], request: DirectorRequest
) -> list[dict[str, Any]]:
    """The anchor item (DirectorItem fields) of each of the reply's moments
    (module docstring) that expand_composites builds the composite from;
    none for a moment past the clip end (moment_problems reports it)."""
    duration = request.signals.duration
    skull = request.preset.skull
    anchors: list[dict[str, Any]] = []
    for moment in moments:
        if moment.t > duration - 1 / request.signals.fps:
            continue
        if moment.move == "skull_moment":
            hold = skull.hold_s if skull else HOLD_MIN_S
            kind, length, params = "freeze_frame", hold, {}
        else:
            kind, length = "audio_fx", BASS_DROP_S
            params = {"effect": "bass_boost", "amount": BASS_DROP_AMOUNT}
        anchors.append(
            {
                "kind": kind,
                "t_start": moment.t,
                "t_end": min(moment.t + length, duration),
                "params": params,
                "reason": moment.reason,
            }
        )
    return anchors


def _whole(plan: ProEditPlan, anchor: EdlItem, kinds: frozenset[EdlKind]) -> bool:
    by_id = {i.id: i for i in plan.items}
    return any(
        anchor.id in g.ids and kinds <= {by_id[n].kind for n in g.ids}
        for g in find_composites(plan.items)
    )


def _replaceable(item: EdlItem, timing: PlanTiming) -> bool:
    return (
        item.source == "auto"
        and not is_loop_ending(item)
        and not is_look(item, timing.duration)
    )


def _builder(
    plan: ProEditPlan,
    items: list[EdlItem],
    timing: PlanTiming,
    budget: IntensityBudget,
    preset: PresetDef,
) -> PlanBuilder:
    builder = PlanBuilder(
        plan, timing, budget, preset.kinds, preset.snap, budgeted=False
    )
    builder.replace(items)
    return builder


def _skull(
    plan: ProEditPlan,
    freeze: EdlItem,
    timing: PlanTiming,
    budget: IntensityBudget,
    preset: PresetDef,
) -> tuple[ProEditPlan, list[PlanNote]]:
    """The plan with a whole Skull Moment from freeze's start (its hold
    kept between HOLD_MIN_S and HOLD_MAX_S and before the clip end) in
    place of freeze and the auto items it clashes with."""
    fps = timing.fps
    at = round(freeze.t_start * fps) / fps
    room = timing.duration - at - SNAP_BACK_WHOOSH_S
    hold = math.floor(min(freeze.t_end - at, HOLD_MAX_S, room) * fps + EPSILON) / fps
    hold = max(hold, HOLD_MIN_S) if room >= HOLD_MIN_S - EPSILON else 0.0
    end = at + hold
    if hold <= 0:
        return plan, []

    def clashes(item: EdlItem) -> bool:
        if item.id == freeze.id:
            return True
        if not _replaceable(item, timing):
            return False
        if item.kind in _VISUAL or item.kind == "freeze_frame":
            return item.t_start < end - EPSILON and at < item.t_end - EPSILON
        sound = item.kind in SKULL_MEMBERS - SKULL_MARKS
        tail = end + SNAP_BACK_WHOOSH_S
        return sound and at - SAME_FRAME_S <= item.t_start < tail - EPSILON

    replaced = [i for i in plan.items if clashes(i)]
    kept = [i for i in plan.items if not clashes(i)]
    builder = _builder(plan, kept, timing, budget, preset)
    what = f"the skull moment at {at:.2f} s ({freeze.reason})"
    moment = Moment("punchline", at, at, what)
    if not place_skull(builder, at, end, moment, preset, what):
        logger.warning(
            "Skull Moment at %.2f s not expanded: %s", at, builder.left_out[-1].why
        )
        return plan, []
    reason = f"replaced by the whole Skull Moment at {at:.2f} s"
    notes = [
        PlanNote(i.id, i.kind, "dropped", reason, i.t_start)
        for i in replaced
        if i.id != freeze.id
    ]
    return builder.plan(), notes


def _drop(
    plan: ProEditPlan,
    boost: EdlItem,
    timing: PlanTiming,
    budget: IntensityBudget,
    preset: PresetDef,
) -> tuple[ProEditPlan, list[PlanNote]]:
    """The plan with a whole bass drop at boost's start in place of boost
    and the auto SFX starting on its frame."""
    at = round(boost.t_start * timing.fps) / timing.fps

    def clashes(item: EdlItem) -> bool:
        on_frame = abs(item.t_start - at) <= SAME_FRAME_S + 0.5 / timing.fps
        sound = item.kind in WHOLE_DROP and _replaceable(item, timing)
        return item.id == boost.id or (sound and on_frame)

    kept = [i for i in plan.items if not clashes(i)]
    builder = _builder(plan, kept, timing, budget, preset)
    if not bass_drop(builder, at, boost.reason):
        logger.warning(
            "bass drop at %.2f s not expanded: %s", at, builder.left_out[-1].why
        )
        return plan, []
    reason = f"replaced by the whole bass drop at {at:.2f} s"
    notes = [
        PlanNote(i.id, i.kind, "dropped", reason, i.t_start)
        for i in plan.items
        if clashes(i) and i.id != boost.id
    ]
    return builder.plan(), notes


def expand_composites(
    plan: ProEditPlan,
    timing: PlanTiming,
    budget: IntensityBudget,
    preset: PresetDef,
) -> tuple[ProEditPlan, list[PlanNote]]:
    """Rebuild every incomplete composite anchor of plan (module docstring):
    with a Skull Moment in the preset, its first max_moments auto freeze
    frames; with bass drops allowed, every auto bass boost. Return the plan
    and a note per item replaced."""
    notes: list[PlanNote] = []
    if preset.skull is not None:
        freezes = [
            i
            for i in plan.items
            if i.kind == "freeze_frame" and _replaceable(i, timing)
        ]
        for freeze in freezes[: preset.skull.max_moments]:
            current = next((i for i in plan.items if i.id == freeze.id), None)
            if current is None or _whole(plan, current, WHOLE_SKULL):
                continue
            plan, replaced = _skull(plan, current, timing, budget, preset)
            notes += replaced
    if {"sfx", "audio_fx"} <= preset.kinds:
        boosts = [
            i
            for i in plan.items
            if i.params.get("effect") == "bass_boost" and _replaceable(i, timing)
        ]
        grouped = {n for g in find_composites(plan.items) for n in g.ids}
        for boost in boosts:
            if boost.id in grouped or not any(i.id == boost.id for i in plan.items):
                continue
            plan, replaced = _drop(plan, boost, timing, budget, preset)
            notes += replaced
    return plan, notes
