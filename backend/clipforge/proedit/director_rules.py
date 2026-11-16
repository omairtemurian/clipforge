"""The rule-based Director (SPEC-v3 3.5): a Pro Edit plan from a clip's
signals, a preset (preset_defs) and an intensity, with no model and no I/O,
the same plan for the same input.

1. The look: the caption style, the preset's grade, vignette and grain and
   the music bed (when the caller chose one) over the whole clip; with
   loop_ending, the loop-friendly ending (retention.add_loop_ending).
2. The rules in the preset's order (earlier rules win where moves clash):
   from the rule's intensity up, on every every-th moment of its signal
   (director_moments) from phase, every move of the rule, or one in turn
   with cycle (director_moves; skull_moment is director_skull). A beat
   rule counts its phase from the first downbeat (the bar's first beat),
   so "every 4, phase 2" is the third beat of every bar. No visual
   interrupt starts in a punchline's reaction hold (pacing.py).
3. At pro and extreme, pattern interrupts (the preset's interrupt kinds in
   turn) in each span longer than the intensity's gap
   (retention.fill_interrupts).
4. Post-processing (postprocess_plan; the builder already fitted the
   budgets and snapping, so it finds little), the whooshes of the preset's
   events (place_whooshes) and the final check (validate_plan and
   budget_problems): a plan the Director returns is always valid.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from clipforge.models import EdlKind, ProEditIntensity, ProEditPlan, ProEditPreset
from clipforge.proedit.audio.sfx_place import place_whooshes
from clipforge.proedit.budgets import (
    INTENSITIES,
    IntensityBudget,
    budget_problems,
    effective_budget,
    interrupt_gaps,
)
from clipforge.proedit.director_build import LeftOut, PlanBuilder
from clipforge.proedit.director_moments import Moment, moments
from clipforge.proedit.director_moves import bass_drop, label, place_kind
from clipforge.proedit.director_music import MusicChoice
from clipforge.proedit.director_skull import skull_moment
from clipforge.proedit.edl import EdlValidationError, validate_plan
from clipforge.proedit.pacing import reaction_holds
from clipforge.proedit.postprocess import postprocess_plan
from clipforge.proedit.preset_defs import PresetDef, Rule
from clipforge.proedit.retention import add_loop_ending, fill_interrupts
from clipforge.proedit.signal_models import ProEditSignals
from clipforge.proedit.signals import plan_timing
from clipforge.proedit.snap import PlanNote

CREATED_BY = "rule_director"


@dataclass(frozen=True)
class RulePlan:
    """A rule-based plan, the notes of its post-processing and whooshes,
    the moves left out and why, and the spans still without a pattern
    interrupt longer than the intensity's gap."""

    plan: ProEditPlan
    notes: list[PlanNote]
    left_out: list[LeftOut]
    interrupt_gaps: list[tuple[float, float]]


def rule_plan(
    signals: ProEditSignals,
    preset: PresetDef,
    preset_id: ProEditPreset,
    intensity: ProEditIntensity,
    music: MusicChoice | None = None,
    plan_id: int = 0,
    version: int = 1,
    style_recipe_id: int | None = None,
    loop_ending: bool = False,
) -> RulePlan:
    """Return the plan of preset (named preset_id) at intensity for the
    clip of signals over music, with a loop-friendly ending if loop_ending
    (module docstring)."""
    beats = music.beats(signals.duration) if music else ()
    timing = plan_timing(signals, beats)
    preset_budget = preset.budgets.get(intensity)
    budget = effective_budget(intensity, preset_budget)
    template = ProEditPlan.model_validate(
        {
            "id": plan_id,
            "clip_id": signals.clip_id,
            "preset": preset_id,
            "intensity": intensity,
            "style_recipe_id": style_recipe_id,
            "version": version,
            "created_by": CREATED_BY,
        }
    )
    holds = reaction_holds(timing, intensity)
    builder = PlanBuilder(template, timing, budget, preset.kinds, preset.snap, holds)
    _place_look(builder, preset, music)
    if loop_ending:
        builder.replace(add_loop_ending(builder.items, timing)[0])
    rank = INTENSITIES.index(intensity)
    for rule in preset.rules:
        if INTENSITIES.index(rule.from_intensity) <= rank:
            found = moments(rule.signal, signals, music)
            first = _bar_start(rule, music, signals.duration)
            _apply_rule(builder, rule, preset, found, first)
    fill_interrupts(builder, preset)
    done = postprocess_plan(builder.plan(), timing, preset_budget, preset.snap)
    placed = place_whooshes(
        done.plan, timing, signals.scene_cuts, preset_budget, preset.whooshes
    )
    plan = placed.plan.model_copy(
        update={
            "rationale": _rationale(preset, intensity, placed.plan, builder.left_out)
        }
    )
    _check(plan, signals.duration, budget)
    return RulePlan(
        plan=plan,
        notes=[*done.notes, *placed.notes],
        left_out=builder.left_out,
        interrupt_gaps=interrupt_gaps(plan.items, signals.duration, budget),
    )


def _place_look(
    builder: PlanBuilder, preset: PresetDef, music: MusicChoice | None
) -> None:
    """Place the preset's whole-clip look and the bed (step 1)."""
    end = builder.timing.duration
    look: list[tuple[EdlKind, BaseModel | None]] = [
        ("caption_style", preset.caption_style),
        ("grade_change", preset.grade),
        ("vignette", preset.vignette),
        ("grain", preset.grain),
    ]
    for kind, params in look:
        if params is not None:
            fields = params.model_dump(mode="json", exclude_none=True)
            builder.place(kind, 0.0, end, fields, f"the {preset.name} look")
    if music is not None:
        bed = {
            "asset": music.asset,
            "gain_db": preset.music.gain_db,
            "offset": music.offset,
        }
        builder.place("music_bed", 0.0, end, bed, f"the {preset.name} music bed")


def _bar_start(rule: Rule, music: MusicChoice | None, duration: float) -> int:
    """The index among the clip's beats of its first downbeat for a beat
    rule (its phase counts from there, step 2); else 0."""
    if rule.signal != "beat" or music is None:
        return 0
    beats, downbeats = music.beats(duration), music.downbeats(duration)
    if not downbeats or downbeats[0] not in beats:
        return 0
    return beats.index(downbeats[0])


def _apply_rule(
    builder: PlanBuilder,
    rule: Rule,
    preset: PresetDef,
    found: list[Moment],
    first: int = 0,
) -> None:
    """Apply rule to its moments (step 2), counting its phase from the
    first-th moment."""
    chosen = found[(first + rule.phase) % rule.every :: rule.every]
    skulls = 0
    for n, moment in enumerate(chosen):
        moves = [rule.moves[n % len(rule.moves)]] if rule.cycle else rule.moves
        for move in moves:
            if move == "skull_moment":
                assert preset.skull is not None
                if skulls < preset.skull.max_moments and skull_moment(
                    builder, moment, preset
                ):
                    skulls += 1
            elif move == "bass_drop":
                at = moment.end if moment.signal == "punchline" else moment.t
                bass_drop(builder, at, moment.what)
            else:
                place_kind(builder, move, moment, preset, rule)


def _rationale(
    preset: PresetDef, intensity: str, plan: ProEditPlan, left_out: list[LeftOut]
) -> str:
    """A short summary of the plan for the owner."""
    kinds = sorted({item.kind for item in plan.items})
    text = (
        f"{preset.name} at {intensity}: {len(plan.items)} edit decisions "
        f"({', '.join(label(k) for k in kinds)}) placed by the preset's rules."
    )
    if left_out:
        text += (
            f" {len(left_out)} moves were left out to keep the plan within its budget."
        )
    return text


def _check(plan: ProEditPlan, duration: float, budget: IntensityBudget) -> None:
    """Raise EdlValidationError when the plan breaks a rule or its budget
    (a Director bug: the builder keeps every plan valid)."""
    validate_plan(plan, duration)
    over = budget_problems(plan.items, budget, duration)
    if over:
        raise EdlValidationError(over)
