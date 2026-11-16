"""Intensity budgets of a Pro Edit plan (SPEC-v3 3.1): how many items of a
kind, and how many effect items in all, may start within any window of time
at each intensity. Presets may lower a budget, never raise it. When a plan is
over budget the lowest-priority items are dropped and each drop says why.
An item over the whole clip is the preset's base look (its grade), not a
move, so no budget counts it when the clip's duration is given.

A composite (composites.py: a Skull Moment, a bass drop) is one unit: it
counts once, at its moment, in each limit any of its items is under (one
effect, one SFX, ...), is kept or dropped whole, and goes before single
items when the budget is short (it is the preset's signature move)."""

from collections.abc import Sequence
from itertools import pairwise
from typing import get_args

from pydantic import BaseModel, ConfigDict, Field

from clipforge.models import EdlItem, EdlKind, ProEditIntensity
from clipforge.proedit.composites import BudgetUnit, budget_units, is_look
from clipforge.proedit.edl import TRACK_OF_KIND, is_loop_ending
from clipforge.proedit.snap import EPSILON, PlanNote

INTENSITIES: tuple[ProEditIntensity, ...] = get_args(ProEditIntensity)
EFFECT_WINDOW_S = 5.0


class Density(BaseModel):
    """At most count items may start within any window_s seconds (a window
    is half-open, so two starts exactly window_s apart are in two)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    count: int = Field(ge=1)
    window_s: float = Field(gt=0)

    def within(self, other: "Density") -> bool:
        """Whether this density is at most as dense as other."""
        return self.count <= other.count and self.window_s >= other.window_s - EPSILON


class IntensityBudget(BaseModel):
    """The budget of one intensity: per-kind densities, the density of the
    effect items together, and the target gap between pattern interrupts
    in seconds (None: no target)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intensity: ProEditIntensity
    kinds: dict[EdlKind, Density]
    effects: Density
    interrupt_s: tuple[float, float] | None


class PresetBudget(BaseModel):
    """A preset's lower limits for one intensity (SPEC-v3 3.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kinds: dict[EdlKind, Density] = Field(default_factory=dict)
    effects: Density | None = None


# The visual moves that count as effect items (whole-clip looks such as
# vignette, grain and the caption style do not).
EFFECT_KINDS: frozenset[EdlKind] = frozenset(
    k for k, track in TRACK_OF_KIND.items() if track in ("zoom", "fx", "overlay")
) | {"grade_change"}
# What counts as a pattern interrupt (SPEC-v3 3.3): a zoom change, an
# effect, a pop or an SFX.
INTERRUPT_KINDS: frozenset[EdlKind] = frozenset(
    k for k, track in TRACK_OF_KIND.items() if track in ("zoom", "fx", "overlay", "sfx")
)

# "1 per N s" of a kind at clean, standard, pro and extreme. SFX is the
# spec's table; the other kinds are analogous.
_SPACING_S: dict[EdlKind, tuple[float, float, float, float]] = {
    "sfx": (6, 4, 2, 1),
    "zoom_punch": (5, 3, 1.5, 0.75),
    "transition": (6, 4, 2, 1),
    "flash": (10, 5, 2, 1),
    "shake": (10, 5, 2, 1),
    "glitch": (15, 8, 3, 1.5),
    "rgb_split": (15, 8, 3, 1.5),
    "text_pop": (4, 3, 2, 1),
    "emoji_pop": (6, 4, 2, 1),
    "overlay": (20, 10, 4, 2),
    "freeze_frame": (30, 15, 6, 3),
    "speed_ramp": (30, 15, 6, 3),
    "slowmo": (30, 15, 6, 3),
    "grade_change": (30, 10, 4, 2),
    "audio_fx": (30, 10, 4, 2),
}
_EFFECTS_PER_WINDOW = (1, 2, 4, 8)
_INTERRUPT_S: tuple[tuple[float, float] | None, ...] = (None, None, (2, 4), (2, 4))

BUDGETS: dict[ProEditIntensity, IntensityBudget] = {
    intensity: IntensityBudget(
        intensity=intensity,
        kinds={k: Density(count=1, window_s=s[n]) for k, s in _SPACING_S.items()},
        effects=Density(count=_EFFECTS_PER_WINDOW[n], window_s=EFFECT_WINDOW_S),
        interrupt_s=_INTERRUPT_S[n],
    )
    for n, intensity in enumerate(INTENSITIES)
}

# Which items are dropped first when a plan is over budget: auto before
# manual and the loop ending (the owner's option), then kinds from the end
# of this list (composites before all of them), then the later item.
KIND_PRIORITY: tuple[EdlKind, ...] = (
    "freeze_frame",
    "zoom_punch",
    "transition",
    "grade_change",
    "overlay",
    "flash",
    "shake",
    "text_pop",
    "sfx",
    "slowmo",
    "speed_ramp",
    "zoom_out_reveal",
    "zoom_push",
    "pan",
    "emoji_pop",
    "glitch",
    "rgb_split",
    "audio_fx",
)
_RANK = {kind: n for n, kind in enumerate(KIND_PRIORITY)}


def effective_budget(
    intensity: ProEditIntensity, preset: PresetBudget | None = None
) -> IntensityBudget:
    """Return the budget of intensity with the preset's limits applied;
    raise ValueError naming every limit the preset would raise."""
    base = BUDGETS[intensity]
    if preset is None:
        return base
    raised = [
        f"{kind} {d.count} per {d.window_s:g} s"
        for kind, d in preset.kinds.items()
        if kind in base.kinds and not d.within(base.kinds[kind])
    ]
    if preset.effects is not None and not preset.effects.within(base.effects):
        raised.append(
            f"effects {preset.effects.count} per {preset.effects.window_s:g} s"
        )
    if raised:
        raise ValueError(
            f"a preset may lower the {intensity} budget, never raise it: "
            + ", ".join(raised)
        )
    return base.model_copy(
        update={
            "kinds": {**base.kinds, **preset.kinds},
            "effects": preset.effects or base.effects,
        }
    )


def most_in_window(starts: Sequence[float], window_s: float) -> int:
    """The largest number of the starts within any window of window_s."""
    points = sorted(starts)
    best, j = 0, 0
    for i, t in enumerate(points):
        while points[j] <= t - window_s + EPSILON:
            j += 1
        best = max(best, i - j + 1)
    return best


def _fits(starts: list[float], t: float, density: Density) -> bool:
    near = [s for s in starts if abs(s - t) < density.window_s]
    return most_in_window([*near, t], density.window_s) <= density.count


def _unit_priority(unit: BudgetUnit) -> tuple[int, int, float, int]:
    owned = any(i.source == "manual" or is_loop_ending(i) for i in unit.items)
    rank = (
        -1
        if unit.move is not None
        else min(_RANK.get(i.kind, len(_RANK)) for i in unit.items)
    )
    return (0 if owned else 1, rank, unit.t, min(i.id for i in unit.items))


def _limits(
    item: EdlItem, budget: IntensityBudget, clip_duration: float | None = None
) -> list[tuple[str, Density]]:
    if is_look(item, clip_duration):
        return []
    limits: list[tuple[str, Density]] = []
    if item.kind in budget.kinds:
        limits.append((item.kind, budget.kinds[item.kind]))
    if item.kind in EFFECT_KINDS:
        limits.append(("effects", budget.effects))
    return limits


def _unit_limits(
    unit: BudgetUnit, budget: IntensityBudget, clip_duration: float | None
) -> list[tuple[str, Density]]:
    """Every limit an item of unit is under, once each."""
    limits: dict[str, Density] = {}
    for item in unit.items:
        for name, density in _limits(item, budget, clip_duration):
            limits.setdefault(name, density)
    return list(limits.items())


def enforce_budgets(
    items: Sequence[EdlItem],
    budget: IntensityBudget,
    clip_duration: float | None = None,
) -> tuple[list[EdlItem], list[PlanNote]]:
    """Keep the units (budget_units: a composite, or one item) in priority
    order while every density of the budget holds; drop the rest. Return
    the kept items in time order and a note naming the broken limit of each
    dropped item. With clip_duration, items over the whole clip (is_look)
    are kept and not counted."""
    starts: dict[str, list[float]] = {}
    kept: list[EdlItem] = []
    notes: list[PlanNote] = []
    for unit in sorted(budget_units(items, clip_duration), key=_unit_priority):
        limits = _unit_limits(unit, budget, clip_duration)
        broken = [
            (name, d)
            for name, d in limits
            if not _fits(starts.get(name, []), unit.t, d)
        ]
        if broken:
            name, d = broken[0]
            reason = (
                f"over the {budget.intensity} budget of {d.count} {name} "
                f"per {d.window_s:g} s"
            )
            if unit.move is not None:
                what = unit.move.replace("_", " ")
                reason = f"part of the {what} at {unit.t:.2f} s, which is {reason}"
            notes += [
                PlanNote(i.id, i.kind, "dropped", reason, i.t_start) for i in unit.items
            ]
            continue
        for name, _ in limits:
            starts.setdefault(name, []).append(unit.t)
        kept += unit.items
    notes.sort(key=lambda n: n.item_id)
    return sorted(kept, key=lambda i: (i.t_start, i.id)), notes


def budget_problems(
    items: Sequence[EdlItem],
    budget: IntensityBudget,
    clip_duration: float | None = None,
) -> list[str]:
    """List every density of the budget that the items break, a composite
    counting once (with clip_duration, items over the whole clip are not
    counted: is_look)."""
    groups: dict[str, tuple[Density, list[float]]] = {}
    for unit in budget_units(items, clip_duration):
        for name, density in _unit_limits(unit, budget, clip_duration):
            groups.setdefault(name, (density, []))[1].append(unit.t)
    problems = []
    for name, (d, starts) in sorted(groups.items()):
        most = most_in_window(starts, d.window_s)
        if most > d.count:
            problems.append(
                f"{most} {name} items start within {d.window_s:g} s; the "
                f"{budget.intensity} budget allows {d.count}"
            )
    return problems


def interrupt_gaps(
    items: Sequence[EdlItem], clip_duration: float, budget: IntensityBudget
) -> list[tuple[float, float]]:
    """The spans longer than the budget's longest interrupt gap in which no
    pattern interrupt starts (from the clip start to its end); empty when
    the intensity has no interrupt target."""
    if budget.interrupt_s is None:
        return []
    longest = budget.interrupt_s[1]
    marks = sorted({i.t_start for i in items if i.kind in INTERRUPT_KINDS})
    bounds = [0.0, *(t for t in marks if 0 < t < clip_duration), clip_duration]
    return [(a, b) for a, b in pairwise(bounds) if b - a > longest + EPSILON]
