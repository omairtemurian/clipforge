"""A Skull Moment and a bass drop are one unit for the budgets and are kept
or dropped whole by post-processing (TASK-237, composites.py)."""

import pytest
from clipforge.models import EdlItem, ProEditIntensity, ProEditPlan
from clipforge.proedit.audio.drop import IMPACT, RISER
from clipforge.proedit.budgets import (
    INTENSITIES,
    budget_problems,
    effective_budget,
    enforce_budgets,
)
from clipforge.proedit.composites import find_composites
from clipforge.proedit.postprocess import postprocess_plan
from clipforge.proedit.snap import PlanTiming
from skull_fakes import item, skull


def _plan(
    items: list[EdlItem], intensity: ProEditIntensity = "standard"
) -> ProEditPlan:
    return ProEditPlan.model_validate(
        {
            "id": 1,
            "clip_id": 1,
            "preset": "skull_moment",
            "intensity": intensity,
            "version": 1,
            "rationale": "test",
            "created_by": "director",
            "items": [i.model_dump() for i in items],
        }
    )


@pytest.mark.parametrize("intensity", INTENSITIES)
def test_budgets_keep_a_skull_moment_whole_as_one_effect(
    intensity: ProEditIntensity,
) -> None:
    others = [
        item(20, "flash", 9.0, 9.2),
        item(21, "glitch", 11.6, 11.8),
        item(22, "sfx", 9.5, 9.9, asset="pop"),
    ]
    budget = effective_budget(intensity, None)

    kept, notes = enforce_budgets([*skull(1, 10.0), *others], budget, 20.0)

    assert {i.id for i in kept} >= set(range(1, 9))
    assert all(n.item_id >= 20 for n in notes)
    assert not budget_problems(kept, budget, 20.0)


def test_a_second_skull_moment_over_budget_is_dropped_whole() -> None:
    items = [*skull(1, 5.0), *skull(11, 12.0)]

    kept, notes = enforce_budgets(items, effective_budget("clean", None), 20.0)

    assert {i.id for i in kept} == set(range(1, 9))
    assert {n.item_id for n in notes} == set(range(11, 19))
    assert all("skull moment" in n.reason for n in notes)
    assert all(n.action == "dropped" and n.t is not None for n in notes)


def test_a_bass_drop_is_one_unit_and_goes_before_single_items() -> None:
    drop = [
        item(1, "sfx", 6.2, 7.8, asset=RISER),
        item(2, "silence_before_drop", 7.8, 8.0),
        item(3, "sfx", 8.0, 9.2, asset=IMPACT),
        item(4, "audio_fx", 8.0, 8.6, effect="bass_boost"),
    ]
    loose = item(5, "sfx", 9.5, 9.9, asset="pop")

    groups = find_composites([*drop, loose], 20.0)
    kept, notes = enforce_budgets(
        [*drop, loose], effective_budget("standard", None), 20.0
    )

    assert [(g.move, g.ids) for g in groups] == [("bass_drop", frozenset({1, 2, 3, 4}))]
    assert {i.id for i in kept} == {1, 2, 3, 4}
    assert [n.item_id for n in notes] == [5]


def test_postprocessing_does_not_snap_a_skull_moment_apart() -> None:
    timing = PlanTiming(30.0, 20.0, word_starts=(10.1,), beats=(10.05,))
    plan = _plan(skull(1, 10.0), "extreme")

    done = postprocess_plan(plan, timing, snap_modes={"shake": "beat"})

    starts = {i.id: i.t_start for i in done.plan.items}
    assert all(starts[n] == pytest.approx(10.0) for n in range(1, 8))
    assert done.notes == []


def test_a_skull_moment_whose_impact_covers_a_punchline_is_dropped_whole() -> None:
    timing = PlanTiming(30.0, 20.0, punchlines=((10.0, 10.4),))
    plan = _plan(skull(1, 10.0), "extreme")

    done = postprocess_plan(plan, timing)

    assert done.plan.items == []
    assert {n.item_id for n in done.notes} == set(range(1, 9))
    assert all(n.action == "dropped" for n in done.notes)
