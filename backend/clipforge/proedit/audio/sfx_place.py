"""SFX placement of a Pro Edit plan (SPEC-v3 3.3): a whoosh on every zoom,
transition, text or emoji pop-in and hard cut (a B-roll's in and out, a
scene cut, a join of the clip's parts), frame-accurate on the visual event.

Each visual event (visual_events) has a motion, in rendered clip seconds:
- zoom_push, zoom_out_reveal and pan: the item's window;
- zoom_punch: its first ease_frames frames (0: instant);
- transition (with params.whoosh): its window (the xfade runs over all of
  it, render/fx_transition);
- text_pop and emoji_pop: the pop-in, render/overlay_plan's intro (INTRO_S;
  BOUNCE_S for bounce; instant for none), at most the item;
- a hard cut: instant.
The whoosh lasts the motion (fit "stretch": the renderer time-stretches it
to the item's length, proedit/audio/sfx_mix) from the motion's start; an
instant or shorter-than-MIN_WHOOSH_S motion gets an INSTANT_WHOOSH_S
whoosh centred on it (its peak, the sound's middle, on the event). The
pack's whoosh nearest the length in ratio is chosen (least stretch), and
successive whooshes cycle through PITCH_VARIANTS so they do not sound
alike.

An event that an SFX of the plan already sounds over keeps it. Events are
placed by PRIORITY (then time) and a whoosh is dropped, with a note, when
it would break the SFX stack limit (edl.py) or the intensity's SFX
density (budgets.py, lowered by the preset's); one that covers a
punchline word is moved to end one frame before the word, or dropped
(snap.protect_punchlines). Run it after postprocess_plan: the plan's
items are on the frame grid.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from clipforge.models import EdlItem, EdlKind, ProEditPlan
from clipforge.proedit.audio.sounds import bundled_named
from clipforge.proedit.budgets import (
    IntensityBudget,
    PresetBudget,
    budget_problems,
    effective_budget,
)
from clipforge.proedit.edl import (
    EmojiPopItem,
    PanItem,
    TextPopItem,
    TransitionItem,
    TypedEdlItem,
    ZoomOutRevealItem,
    ZoomPunchItem,
    ZoomPushItem,
    parse_item,
    plan_problems,
)
from clipforge.proedit.render.overlay_plan import BOUNCE_S, INTRO_S
from clipforge.proedit.snap import EPSILON, PlanNote, PlanTiming, protect_punchlines

EventKind = Literal["transition", "zoom", "cut", "pop"]
ALL_EVENTS: frozenset[EventKind] = frozenset({"transition", "zoom", "cut", "pop"})
PRIORITY: tuple[EventKind, ...] = ("transition", "zoom", "cut", "pop")
WHOOSHES: tuple[str, ...] = ("whoosh_swift", "whoosh_soft")
PITCH_VARIANTS: tuple[float, ...] = (0.0, -2.0, 2.0, -1.0, 1.0)
WHOOSH_GAIN_DB = -8.0
MIN_WHOOSH_S = 0.1
INSTANT_WHOOSH_S = 0.3
SFX_KIND: EdlKind = "sfx"


@dataclass(frozen=True)
class VisualEvent:
    """A visual event of kind whose motion runs from start to end seconds
    (equal: instant); what names it in the whoosh's reason."""

    kind: EventKind
    start: float
    end: float
    what: str

    @property
    def motion_s(self) -> float:
        """The motion's length in seconds."""
        return self.end - self.start


@dataclass(frozen=True)
class SfxPlacement:
    """The plan with its whooshes and a note per whoosh moved or dropped."""

    plan: ProEditPlan
    notes: list[PlanNote]


def pop_in_s(item: TextPopItem | EmojiPopItem, fps: int) -> float:
    """Return how long item's pop-in animation lasts (at most the item)."""
    animation = item.params.animation
    if animation == "none":
        return 0.0
    intro = BOUNCE_S if animation == "bounce" else INTRO_S
    frames = max(round(intro * fps), 1)
    return min(frames / fps, item.t_end - item.t_start)


def item_event(item: TypedEdlItem, fps: int) -> VisualEvent | None:
    """Return the visual event of item, or None if it has none."""
    what = f"the {item.kind} item {item.id}"
    if isinstance(item, ZoomPushItem | ZoomOutRevealItem | PanItem):
        return VisualEvent("zoom", item.t_start, item.t_end, what)
    if isinstance(item, ZoomPunchItem):
        ease = item.params.ease_frames / fps
        return VisualEvent("zoom", item.t_start, item.t_start + ease, what)
    if isinstance(item, TransitionItem) and item.params.whoosh:
        return VisualEvent("transition", item.t_start, item.t_end, what)
    if isinstance(item, TextPopItem | EmojiPopItem):
        return VisualEvent(
            "pop", item.t_start, item.t_start + pop_in_s(item, fps), what
        )
    return None


def visual_events(
    items: Sequence[TypedEdlItem], cuts: Sequence[float], fps: int
) -> list[VisualEvent]:
    """Return the visual events of items and the hard cuts at cuts (rendered
    clip seconds), by PRIORITY, then time."""
    events = [e for item in items if (e := item_event(item, fps)) is not None]
    events += [VisualEvent("cut", t, t, f"the cut at {t:g} s") for t in cuts]
    return sorted(events, key=lambda e: (PRIORITY.index(e.kind), e.start, e.what))


def whoosh_frames(event: VisualEvent, timing: PlanTiming) -> tuple[int, int] | None:
    """Return the (first, end) frames of event's whoosh (module docstring),
    kept inside the clip; None if not even a frame of it fits."""
    fps = timing.fps
    if event.motion_s >= MIN_WHOOSH_S - EPSILON:
        start, end = round(event.start * fps), round(event.end * fps)
    else:
        length = max(round(INSTANT_WHOOSH_S * fps), 1)
        start = round((event.start + event.end) / 2 * fps) - length // 2
        end = start + length
    start, end = max(start, 0), min(end, timing.last_frame)
    return (start, end) if end > start else None


def whoosh_asset(seconds: float) -> str:
    """Return the pack's whoosh nearest seconds in ratio (least stretch)."""
    lengths = {name: _bundled_seconds(name) for name in WHOOSHES}
    return min(WHOOSHES, key=lambda name: abs(math.log(lengths[name] / seconds)))


def _bundled_seconds(name: str) -> float:
    sound = bundled_named(name)
    if sound is None:
        raise LookupError(f"the bundled pack has no {name}")
    return sound.seconds


def _covered(start: float, end: float, sfx: Sequence[EdlItem]) -> bool:
    """Whether an SFX of sfx sounds during start-end (or at an instant)."""
    return any(s.t_start < max(end, start + EPSILON) and start < s.t_end for s in sfx)


def place_whooshes(
    plan: ProEditPlan,
    timing: PlanTiming,
    cuts: Sequence[float] = (),
    preset_budget: PresetBudget | None = None,
    events: frozenset[EventKind] = ALL_EVENTS,
) -> SfxPlacement:
    """Add a whoosh SFX item for each visual event of plan's items and the
    hard cuts at cuts (rendered clip seconds) whose kind is in events, as
    the module docstring says; return the plan and the notes."""
    budget = effective_budget(plan.intensity, preset_budget)
    typed = [parse_item(item) for item in plan.items]
    sfx = [item for item in plan.items if item.kind == SFX_KIND]
    added: list[EdlItem] = []
    notes: list[PlanNote] = []
    next_id = max((item.id for item in plan.items), default=0) + 1
    fps = round(timing.fps)
    for event in visual_events(typed, cuts, fps):
        frames = whoosh_frames(event, timing) if event.kind in events else None
        if frames is None or _covered(event.start, event.end, [*sfx, *added]):
            continue
        candidate = _whoosh(next_id, event, frames, len(added), timing.fps)
        next_id += 1
        placed, note = _fit(candidate, [*sfx, *added], timing, plan, budget)
        if note is not None:
            notes.append(note)
        if placed is not None:
            added.append(placed)
    items = sorted([*plan.items, *added], key=lambda i: (i.t_start, i.id))
    return SfxPlacement(plan.model_copy(update={"items": items}), notes)


def _whoosh(
    id: int, event: VisualEvent, frames: tuple[int, int], index: int, fps: float
) -> EdlItem:
    start, end = frames[0] / fps, frames[1] / fps
    pitch = PITCH_VARIANTS[index % len(PITCH_VARIANTS)]
    return EdlItem(
        id=id,
        kind=SFX_KIND,
        t_start=start,
        t_end=end,
        params={
            "asset": whoosh_asset(end - start),
            "gain_db": WHOOSH_GAIN_DB,
            "pitch_semitones": pitch,
            "fit": "stretch",
        },
        reason=f"whoosh on {event.what} ({end - start:.2f} s)",
        source="auto",
    )


def _fit(
    candidate: EdlItem,
    sfx: list[EdlItem],
    timing: PlanTiming,
    plan: ProEditPlan,
    budget: IntensityBudget,
) -> tuple[EdlItem | None, PlanNote | None]:
    """Return the candidate as placed (moved off a punchline) or None, and
    the note of what happened to it (None: placed where planned)."""
    moved, notes = protect_punchlines([*sfx, candidate], timing)
    placed = next((i for i in moved if i.id == candidate.id), None)
    note = next((n for n in notes if n.item_id == candidate.id), None)
    if placed is None:
        return None, note
    trial = plan.model_copy(update={"items": [*sfx, placed]})
    problems = plan_problems(trial, timing.duration)
    others = [i for i in plan.items if i.kind != SFX_KIND]
    problems += budget_problems([*others, *sfx, placed], budget, timing.duration)
    if problems:
        reason = f"the whoosh would break a rule: {problems[0]}"
        return None, PlanNote(
            candidate.id, SFX_KIND, "dropped", reason, candidate.t_start
        )
    return placed, note
