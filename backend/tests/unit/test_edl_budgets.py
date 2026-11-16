"""Pro Edit intensity budgets (SPEC-v3 3.1) with exact counts, and the whole
post-processing: snapping, punchline protection, then budgets."""

import random
from itertools import pairwise

import pytest
from clipforge.models import EdlItem, EdlKind, ProEditIntensity
from clipforge.proedit.budgets import (
    BUDGETS,
    EFFECT_KINDS,
    INTENSITIES,
    Density,
    PresetBudget,
    budget_problems,
    effective_budget,
    enforce_budgets,
    interrupt_gaps,
    is_look,
    most_in_window,
)
from clipforge.proedit.edl import validate_plan
from clipforge.proedit.postprocess import postprocess_plan
from clipforge.proedit.snap import PlanTiming
from edl_fakes import item, plan, times

# --- budgets ----------------------------------------------------------------


def every(
    kind: EdlKind, step: float, until: float, length: float = 0.2
) -> list[EdlItem]:
    count = round(until / step)
    return [item(n + 1, kind, n * step, n * step + length) for n in range(count)]


@pytest.mark.parametrize(
    ("intensity", "kept_starts"),
    [
        ("clean", [0, 6, 12, 18, 24]),
        ("standard", [0, 4, 8, 12, 16, 20, 24, 28]),
        ("pro", [float(t) for t in range(0, 30, 2)]),
        ("extreme", [float(t) for t in range(30)]),
    ],
)
def test_sfx_density_per_intensity_with_exact_counts(
    intensity: ProEditIntensity, kept_starts: list[float]
) -> None:
    sfx = every("sfx", 1.0, 30.0)
    kept, notes = enforce_budgets(sfx, BUDGETS[intensity])
    assert [i.t_start for i in kept] == kept_starts
    assert len(notes) == 30 - len(kept_starts)
    assert all(n.action == "dropped" for n in notes)
    window = {"clean": 6, "standard": 4, "pro": 2, "extreme": 1}[intensity]
    if notes:
        assert notes[0].reason == f"over the {intensity} budget of 1 sfx per {window} s"
    assert budget_problems(kept, BUDGETS[intensity]) == []


@pytest.mark.parametrize(
    ("intensity", "count"),
    [("clean", 6), ("standard", 10), ("pro", 20), ("extreme", 30)],
)
def test_zoom_punch_density_per_intensity(
    intensity: ProEditIntensity, count: int
) -> None:
    kept, _ = enforce_budgets(every("zoom_punch", 0.5, 30.0), BUDGETS[intensity])
    assert len(kept) == count
    assert budget_problems(kept, BUDGETS[intensity]) == []


def test_effect_items_per_five_seconds_keep_the_highest_priority() -> None:
    items = [
        item(1, "zoom_push", 0.0, 0.5),
        item(2, "flash", 1.0, 1.1),
        item(3, "text_pop", 2.0, 2.5),
        item(4, "zoom_push", 6.0, 6.5),
    ]
    kept, notes = enforce_budgets(items, BUDGETS["clean"])
    assert [i.id for i in kept] == [2, 4]
    assert [(n.item_id, n.reason) for n in notes] == [
        (1, "over the clean budget of 1 effects per 5 s"),
        (3, "over the clean budget of 1 effects per 5 s"),
    ]


def test_manual_items_outrank_auto_items() -> None:
    items = [item(1, "sfx", 1.0, 1.2), item(2, "sfx", 3.0, 3.2, source="manual")]
    kept, notes = enforce_budgets(items, BUDGETS["clean"])
    assert [i.id for i in kept] == [2]
    assert [n.item_id for n in notes] == [1]


def test_unbudgeted_kinds_are_never_dropped() -> None:
    items = [
        item(1, "vignette", 0, 30),
        item(2, "grain", 0, 30),
        item(3, "caption_style", 0, 30),
        item(4, "music_bed", 0, 30),
    ]
    kept, notes = enforce_budgets(items, BUDGETS["clean"])
    assert len(kept) == 4 and notes == []
    assert not EFFECT_KINDS & {"vignette", "grain", "caption_style", "sfx"}


def test_budgets_grow_from_clean_to_extreme() -> None:
    assert [BUDGETS[i].effects.count for i in INTENSITIES] == [1, 2, 4, 8]
    assert [BUDGETS[i].kinds["sfx"].window_s for i in INTENSITIES] == [6, 4, 2, 1]
    assert [BUDGETS[i].interrupt_s for i in INTENSITIES] == [None, None, (2, 4), (2, 4)]
    for lower, higher in pairwise(INTENSITIES):
        for kind, density in BUDGETS[higher].kinds.items():
            assert BUDGETS[lower].kinds[kind].within(density), (kind, lower)


def test_a_preset_may_lower_a_budget_but_never_raise_it() -> None:
    lowered = effective_budget(
        "pro",
        PresetBudget(
            kinds={
                "sfx": Density(count=1, window_s=3),
                "vignette": Density(count=1, window_s=30),
            },
            effects=Density(count=2, window_s=5),
        ),
    )
    assert lowered.kinds["sfx"] == Density(count=1, window_s=3)
    assert lowered.kinds["flash"] == BUDGETS["pro"].kinds["flash"]
    assert lowered.effects.count == 2
    kept, _ = enforce_budgets(every("sfx", 1.0, 12.0), lowered)
    assert [i.t_start for i in kept] == [0, 3, 6, 9]
    with pytest.raises(
        ValueError, match=r"never raise it: sfx 1 per 1 s, effects 9 per 5 s"
    ):
        effective_budget(
            "pro",
            PresetBudget(
                kinds={"sfx": Density(count=1, window_s=1)},
                effects=Density(count=9, window_s=5),
            ),
        )
    assert effective_budget("clean") is BUDGETS["clean"]


def test_most_in_window_counts_half_open_windows() -> None:
    assert most_in_window([0, 5, 5.5, 10], 5) == 2
    assert most_in_window([0, 1, 2, 3, 4.99], 5) == 5
    assert most_in_window([], 5) == 0


def test_budget_problems_name_the_limit() -> None:
    assert budget_problems(every("sfx", 1.0, 3.0), BUDGETS["clean"]) == [
        "3 sfx items start within 6 s; the clean budget allows 1"
    ]


def test_whole_clip_looks_are_not_counted_by_any_budget() -> None:
    grade = item(1, "grade_change", 0, 30, params={"look": "bw"})
    looks = [grade, item(2, "vignette", 0, 30), item(3, "grain", 0, 30)]
    effects = [item(4, "zoom_punch", 0, 0.5), item(5, "flash", 1, 1.1)]
    budget = BUDGETS["standard"]

    assert all(is_look(i, 30.0) for i in looks)
    assert not is_look(grade, 31.0)
    assert budget_problems([*looks, *effects], budget, 30.0) == []
    assert budget_problems([*looks, *effects], budget) != []
    kept, notes = enforce_budgets([*looks, *effects], budget, 30.0)
    assert [i.id for i in kept] == [1, 2, 3, 4, 5] and notes == []


def test_interrupt_gaps_at_pro_and_none_at_clean() -> None:
    items = [
        item(1, "zoom_punch", 1, 1.3),
        item(2, "sfx", 4, 4.2),
        item(3, "flash", 10, 10.1),
    ]
    items.append(item(4, "vignette", 0, 12))
    assert interrupt_gaps(items, 12, BUDGETS["pro"]) == [(4, 10)]
    assert interrupt_gaps(items, 12, BUDGETS["clean"]) == []
    assert interrupt_gaps([], 9, BUDGETS["extreme"]) == [(0, 9)]


# --- the whole post-processing ----------------------------------------------


def random_items(seed: int, duration: float) -> list[EdlItem]:
    """A valid plan: per kind, items one after the other with gaps."""
    rng = random.Random(seed)
    items: list[EdlItem] = []
    for kind in ("sfx", "zoom_punch", "flash", "text_pop"):
        t = rng.uniform(0, 0.5)
        while t < duration - 1:
            length = rng.uniform(0.1, 0.4)
            items.append(item(len(items) + 1, kind, round(t, 3), round(t + length, 3)))
            t += length + rng.uniform(0.05, 1.2)
    return items


@pytest.mark.parametrize("intensity", INTENSITIES)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_postprocessed_plans_are_valid_on_the_grid_and_in_budget(
    intensity: ProEditIntensity, seed: int
) -> None:
    duration = 20.0
    rng = random.Random(seed)
    timing = PlanTiming(
        fps=30,
        duration=duration,
        word_starts=tuple(round(rng.uniform(0, duration), 3) for _ in range(40)),
        beats=tuple(n * 0.4 for n in range(50)),
        punchlines=((6.0, 6.4), (14.2, 14.5)),
    )
    result = postprocess_plan(plan(random_items(seed, duration), intensity), timing)
    items = result.plan.items
    validate_plan(result.plan, duration)
    assert budget_problems(items, BUDGETS[intensity]) == []
    for i in items:
        for t in (i.t_start, i.t_end):
            assert t * 30 == pytest.approx(round(t * 30), abs=1e-9)
        if i.kind == "sfx":
            assert all(i.t_end <= w0 or i.t_start >= w1 for w0, w1 in timing.punchlines)
    again = postprocess_plan(plan(random_items(seed, duration), intensity), timing)
    assert again == result


def test_postprocess_snaps_protects_and_budgets_in_order() -> None:
    timing = PlanTiming(fps=30, duration=12, beats=(2.0, 4.0), punchlines=((5.0, 5.4),))
    items = [
        item(1, "flash", 2.05, 2.15),
        item(2, "sfx", 4.9, 5.2),
        item(3, "sfx", 5.5, 5.7),
        item(4, "zoom_punch", 6.0, 6.3),
    ]
    result = postprocess_plan(plan(items, "clean"), timing)
    # The flash snaps to the beat at 2 s, but at clean the zoom punch
    # outranks it in the one effect per 5 s; the zoom punch starts in the
    # 1 s reaction hold after the punchline, so it moves to its end.
    assert times(result.plan.items) == {2: (140 / 30, 149 / 30), 4: (6.4, 6.7)}
    assert [(n.item_id, n.action) for n in result.notes] == [
        (2, "moved"),
        (4, "moved"),
        (1, "dropped"),
        (3, "dropped"),
    ]
    assert result.interrupt_gaps == []
    pro = postprocess_plan(plan(items, "pro"), timing)
    assert [i.id for i in pro.plan.items] == [1, 2, 4]
    assert [(n.item_id, n.reason) for n in pro.notes][1:] == [
        (3, "over the pro budget of 1 sfx per 2 s")
    ]
    assert pro.interrupt_gaps == [(6.0, 12.0)]
