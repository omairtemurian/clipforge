"""Retention moves of a Pro Edit plan (SPEC-v3 3.3, TASK-233): pattern
interrupts every 2-4 s at pro and extreme (the rule-based Director and an
LLM plan), the reaction holds after punchlines and the loop-friendly
ending."""

import json
from pathlib import Path

import pytest
from clipforge.models import EdlItem, ProEditIntensity, ProEditPlan, ProEditPreset
from clipforge.proedit.budgets import INTERRUPT_KINDS, effective_budget
from clipforge.proedit.director_build import PlanBuilder
from clipforge.proedit.director_catalog import asset_catalog
from clipforge.proedit.director_llm import finish_plan
from clipforge.proedit.director_prompt import DirectorRequest
from clipforge.proedit.director_rules import rule_plan
from clipforge.proedit.edl import is_loop_ending, validate_plan
from clipforge.proedit.pacing import HOLD_S, broken_hold, reaction_holds
from clipforge.proedit.postprocess import postprocess_plan
from clipforge.proedit.preset_defs import get_preset, load_presets
from clipforge.proedit.retention import LOOP_S, add_loop_ending, fill_plan
from clipforge.proedit.signal_models import ProEditSignals
from clipforge.proedit.signals import plan_timing
from clipforge.proedit.snap import PlanTiming
from edl_fakes import item, plan

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "proedit_signals_expected.json"
)
SIGNALS = ProEditSignals.model_validate(json.loads(FIXTURE.read_text()))
TIMING = plan_timing(SIGNALS)
PRESETS: list[ProEditPreset] = sorted(load_presets())
HEAVY: list[ProEditIntensity] = ["pro", "extreme"]


def interrupt_starts(items: list[EdlItem]) -> list[float]:
    """The starts of the plan's own interrupts (whooshes and the loop
    ending follow other moves, so they are left out)."""
    return sorted(
        {
            i.t_start
            for i in items
            if i.kind in INTERRUPT_KINDS
            and not i.reason.startswith("whoosh on")
            and not is_loop_ending(i)
        }
    )


def filled(items: list[EdlItem]) -> list[EdlItem]:
    return [i for i in items if "a pattern interrupt at" in i.reason]


def assert_spacing(items: list[EdlItem], duration: float) -> None:
    """Every gap between interrupt starts (from the clip start to its end)
    is at most 4 s, and every filled interrupt starts 2-4 s after the
    interrupt before it."""
    starts = interrupt_starts(items)
    bounds = [0.0, *starts, duration]
    assert max(b - a for a, b in zip(bounds, bounds[1:], strict=False)) <= 4 + 1e-6
    for added in filled(items):
        before = max(t for t in [0.0, *starts] if t < added.t_start - 1e-6)
        assert 2 - 1e-6 <= added.t_start - before <= 4 + 1e-6


def request(intensity: ProEditIntensity, loop: bool = False) -> DirectorRequest:
    preset = get_preset("cinematic")
    return DirectorRequest(
        signals=SIGNALS,
        preset=preset,
        preset_id="cinematic",
        intensity=intensity,
        catalog=tuple(asset_catalog()),
        plan_id=4,
        loop_ending=loop,
    )


def bare(intensity: ProEditIntensity, items: list[EdlItem]) -> ProEditPlan:
    return plan(items, intensity).model_copy(
        update={"preset": "cinematic", "created_by": "llm_director"}
    )


@pytest.mark.parametrize("intensity", HEAVY)
@pytest.mark.parametrize("preset", PRESETS)
def test_rule_plans_have_an_interrupt_every_2_to_4_s(
    preset: ProEditPreset, intensity: ProEditIntensity
) -> None:
    result = rule_plan(SIGNALS, get_preset(preset), preset, intensity)
    assert result.interrupt_gaps == []
    assert_spacing(result.plan.items, SIGNALS.duration)


@pytest.mark.parametrize("intensity", HEAVY)
def test_an_llm_plan_without_moves_gets_interrupts_every_2_to_4_s(
    intensity: ProEditIntensity,
) -> None:
    finished, _, problems = finish_plan(bare(intensity, []), request(intensity))
    assert problems == []
    starts = interrupt_starts(finished.items)
    assert len(filled(finished.items)) == len(starts) >= SIGNALS.duration // 4
    gaps = [b - a for a, b in zip([0.0, *starts], starts, strict=False)]
    assert all(2 - 1e-6 <= gap <= 4 + 1e-6 for gap in gaps)
    assert SIGNALS.duration - starts[-1] <= 4 + 1e-6


def test_lighter_intensities_get_no_interrupts_filled() -> None:
    for intensity in ("clean", "standard"):
        finished, _, _ = finish_plan(bare(intensity, []), request(intensity))
        assert filled(finished.items) == []


def test_fill_plan_keeps_the_items_and_their_ids() -> None:
    zoom = item(1, "zoom_punch", 1.0, 1.3)
    budget = effective_budget("pro")
    done, added = fill_plan(bare("pro", [zoom]), TIMING, budget, get_preset("glitch"))
    assert done.items[0] == zoom and [i.id for i in added] == list(
        range(2, len(added) + 2)
    )
    assert_spacing(done.items, SIGNALS.duration)


def test_reaction_holds_follow_each_punchline_by_intensity() -> None:
    timing = PlanTiming(fps=30, duration=12, punchlines=((5.0, 5.4), (11.6, 11.8)))
    assert reaction_holds(timing, "pro") == [
        pytest.approx((5.4 + 1 / 30, 5.4 + HOLD_S["pro"])),
        pytest.approx((11.8 + 1 / 30, 12.0)),
    ]
    assert all(0.5 <= hold <= 1.0 for hold in HOLD_S.values())


@pytest.mark.parametrize("intensity", HEAVY)
@pytest.mark.parametrize("preset", PRESETS)
def test_no_visual_interrupt_starts_in_a_reaction_hold(
    preset: ProEditPreset, intensity: ProEditIntensity
) -> None:
    result = rule_plan(SIGNALS, get_preset(preset), preset, intensity)
    holds = reaction_holds(TIMING, intensity)
    assert [i for i in result.plan.items if broken_hold(i, holds, TIMING)] == []


def test_post_processing_moves_or_drops_what_breaks_a_hold() -> None:
    timing = PlanTiming(fps=30, duration=12, punchlines=((5.0, 5.4),))
    items = [
        item(1, "zoom_punch", 5.4, 5.7),  # the punchline's own reaction
        item(2, "flash", 5.6, 5.7),  # moves to the hold's end (6.0 s)
        item(3, "glitch", 5.7, 5.8),  # at 6.0-6.1 it would clash with item 2
        item(4, "shake", 5.9, 6.0),  # a layer over the shot: it stays
        item(6, "sfx", 5.6, 5.8),  # sound is no picture change
        item(7, "text_pop", 5.6, 5.9, source="manual"),
    ]
    done = postprocess_plan(plan(items, "pro"), timing)
    by_id = {i.id: (i.t_start, i.t_end) for i in done.plan.items}
    assert by_id[2] == pytest.approx((6.0, 6.1))
    assert by_id[4] == (5.9, 6.0)
    assert 3 not in by_id and by_id[1] == (5.4, 5.7)
    assert by_id[6] == (5.6, 5.8) and by_id[7] == (5.6, 5.9)
    actions = {n.item_id: n.action for n in done.notes}
    assert actions == {2: "moved", 3: "dropped"}


def test_the_builder_leaves_out_moves_in_a_hold() -> None:
    timing = PlanTiming(fps=30, duration=12, punchlines=((5.0, 5.4),))
    holds = reaction_holds(timing, "pro")
    builder = PlanBuilder(
        bare("pro", []), timing, effective_budget("pro"), {"flash"}, holds=holds
    )
    assert builder.place("flash", 5.6, 5.7, {}, "test") is None
    assert "reaction hold" in builder.left_out[0].why
    assert builder.place("flash", 6.0, 6.1, {}, "test") is not None


@pytest.mark.parametrize("preset", PRESETS)
def test_a_loop_ending_ends_every_rule_plan_on_its_last_frame(
    preset: ProEditPreset,
) -> None:
    for intensity in ("clean", "extreme"):
        result = rule_plan(
            SIGNALS, get_preset(preset), preset, intensity, loop_ending=True
        )
        (loop,) = [i for i in result.plan.items if is_loop_ending(i)]
        assert loop.t_end == SIGNALS.duration
        assert loop.t_start == pytest.approx(SIGNALS.duration - LOOP_S)
        assert loop.params == {"type": "loop", "whoosh": False}
        validate_plan(result.plan, SIGNALS.duration)
    plain = rule_plan(SIGNALS, get_preset(preset), preset, "pro")
    assert not any(is_loop_ending(i) for i in plain.plan.items)


def test_the_loop_ending_wins_over_auto_moves_but_not_manual_ones() -> None:
    timing = PlanTiming(fps=30, duration=12)
    auto = [item(1, "glitch", 11.6, 11.9), item(2, "grade_change", 0, 12)]
    items, notes = add_loop_ending(auto, timing)
    assert [i.id for i in items] == [2, 3] and is_loop_ending(items[1])
    assert [(n.item_id, n.action) for n in notes] == [(1, "dropped")]
    assert add_loop_ending(items, timing) == (items, [])
    manual = [item(1, "glitch", 11.6, 11.9, source="manual")]
    assert add_loop_ending(manual, timing) == (manual, [])


def test_post_processing_keeps_the_loop_ending_at_the_end() -> None:
    # A beat near its start would snap a transition, and at clean the one
    # effect per 5 s would keep the flash over it: the loop ending stays.
    timing = PlanTiming(fps=30, duration=12, beats=(11.68,))
    items, _ = add_loop_ending([item(1, "flash", 9.0, 9.1)], timing)
    done = postprocess_plan(plan(items, "clean"), timing)
    loop = done.plan.items[-1]
    assert is_loop_ending(loop) and (loop.t_start, loop.t_end) == (11.7, 12.0)
    assert [n.item_id for n in done.notes] == [1]


def test_an_llm_plan_gets_the_loop_ending_it_was_asked_for() -> None:
    finished, notes, problems = finish_plan(bare("pro", []), request("pro", True))
    assert problems == [] and is_loop_ending(finished.items[-1])
    plain, _, _ = finish_plan(bare("pro", []), request("pro"))
    assert not any(is_loop_ending(i) for i in plain.items)
