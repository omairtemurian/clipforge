"""Snapping of a Pro Edit plan's times (SPEC-v3 3.1), run by code after any
planner: every time lands on the clip's frame grid (`round(t * fps) / fps`);
items that snap to words start on the nearest word start within 0.25 s, items
that snap to beats on the nearest beat within 0.12 s (else the word rule,
else the frame rule). An SFX never sounds over a punchline word: it is moved
to end one frame before the word starts, or dropped. Snapping never makes
items overlap that did not: a snapped place that would falls back to the
plain frame grid. The items of a composite (composites.py, passed as fixed)
stay together on the frame grid: they are not snapped apart, and a fixed SFX
over a punchline word is dropped, not moved, so the caller drops the whole
composite."""

import bisect
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, get_args

from clipforge.models import EdlItem, EdlKind
from clipforge.proedit.edl import STACK_GROUPS, STACKABLE, excludes, is_loop_ending

SnapMode = Literal["frame", "word", "beat"]
NoteAction = Literal["moved", "dropped"]

WORD_WINDOW_S = 0.25
BEAT_WINDOW_S = 0.12
EPSILON = 1e-6

# Caption, text and emphasis items start on words; music-driven kinds on
# beats; the rest on the frame grid only. Presets may pass other modes.
DEFAULT_SNAP: dict[EdlKind, SnapMode] = {kind: "frame" for kind in get_args(EdlKind)}
DEFAULT_SNAP.update(
    {
        "zoom_punch": "word",
        "text_pop": "word",
        "emoji_pop": "word",
        "caption_style": "word",
        "flash": "beat",
        "shake": "beat",
        "glitch": "beat",
        "rgb_split": "beat",
        "transition": "beat",
        "silence_before_drop": "beat",
    }
)
# The silence before a drop ends on the drop, so its end is what snaps.
END_ANCHORED: frozenset[EdlKind] = frozenset({"silence_before_drop"})


@dataclass(frozen=True)
class PlanTiming:
    """What the times of a plan snap to: the clip's frame rate and duration,
    the word starts and music beats in seconds of the clip, and the
    punchline word spans (start, end) that no SFX may cover."""

    fps: float
    duration: float
    word_starts: tuple[float, ...] = ()
    beats: tuple[float, ...] = ()
    punchlines: tuple[tuple[float, float], ...] = ()

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise ValueError("fps must be positive")
        if self.duration * self.fps < 1:
            raise ValueError("the clip must last at least one frame")
        object.__setattr__(self, "word_starts", tuple(sorted(self.word_starts)))
        object.__setattr__(self, "beats", tuple(sorted(self.beats)))

    @property
    def last_frame(self) -> int:
        """The frame index of the clip's end."""
        return math.floor(self.duration * self.fps + EPSILON)


@dataclass(frozen=True)
class PlanNote:
    """What post-processing did to an item and why (shown with the plan);
    t is the item's start in clip seconds before it was moved or dropped
    (None: not known)."""

    item_id: int
    kind: EdlKind
    action: NoteAction
    reason: str
    t: float | None = None

    def line(self) -> str:
        """The note as one line of the run's notes:
        "Dropped shake at 16.37 s: why"."""
        at = "" if self.t is None else f" at {self.t:.2f} s"
        return f"{self.action.capitalize()} {self.kind}{at}: {self.reason}"


@dataclass(frozen=True)
class _Placed:
    kind: EdlKind
    start: int
    end: int


def nearest(times: Sequence[float], t: float, window: float) -> float | None:
    """Return the time of sorted times nearest to t (the earlier on a tie)
    when it is at most window seconds away, else None."""
    i = bisect.bisect_left(times, t)
    candidates = times[max(0, i - 1) : i + 1]
    if not candidates:
        return None
    best = min(candidates, key=lambda x: (abs(x - t), x))
    return best if abs(best - t) <= window + EPSILON else None


def snap_target(t: float, mode: SnapMode, timing: PlanTiming) -> float:
    """Return where time t snaps to before the frame grid: a beat within
    0.12 s (beat mode), else a word start within 0.25 s (beat and word
    modes), else t itself."""
    if mode == "beat":
        beat = nearest(timing.beats, t, BEAT_WINDOW_S)
        if beat is not None:
            return beat
    if mode in ("beat", "word"):
        word = nearest(timing.word_starts, t, WORD_WINDOW_S)
        if word is not None:
            return word
    return t


def _frame_place(item: EdlItem, timing: PlanTiming) -> tuple[int, int]:
    """The item on the frame grid: each time rounded, at least one frame
    long and not past the clip end."""
    start = round(item.t_start * timing.fps)
    end = min(round(item.t_end * timing.fps), timing.last_frame)
    if end <= start:
        end = start + 1
    if end > timing.last_frame:
        start, end = timing.last_frame - 1, timing.last_frame
    return start, end


def _anchored_place(
    item: EdlItem, mode: SnapMode, timing: PlanTiming
) -> tuple[int, int] | None:
    """The item moved (its length kept) so that its anchor is on the snap
    target; None when the target is the item's own time or it does not fit
    in the clip."""
    anchor = item.t_end if item.kind in END_ANCHORED else item.t_start
    target = snap_target(anchor, mode, timing)
    if target == anchor:
        return None
    length = max(1, round((item.t_end - item.t_start) * timing.fps))
    frame = round(target * timing.fps)
    start, end = (
        (frame - length, frame)
        if item.kind in END_ANCHORED
        else (frame, frame + length)
    )
    if start < 0 or end > timing.last_frame:
        return None
    return start, end


def _conflicts(kind: EdlKind, start: int, end: int, placed: Iterable[_Placed]) -> bool:
    """Whether an item of kind at frames start-end would overlap a placed
    item it excludes (edl.excludes), or exceed its stack group's limit."""
    if kind not in STACKABLE:
        return any(
            excludes(kind, p.kind) and p.start < end and start < p.end for p in placed
        )
    group, limit = next((g, n) for g, n in STACK_GROUPS if kind in g)
    members = [p for p in placed if p.kind in group and p.start < end and start < p.end]
    instants = [start] + [p.start for p in members if p.start > start]
    return any(
        sum(1 for p in members if p.start <= t < p.end) + 1 > limit for t in instants
    )


def _at(item: EdlItem, start: int, end: int, fps: float) -> EdlItem:
    return item.model_copy(update={"t_start": start / fps, "t_end": end / fps})


def snap_items(
    items: Sequence[EdlItem],
    timing: PlanTiming,
    modes: Mapping[EdlKind, SnapMode] | None = None,
    fixed: frozenset[int] = frozenset(),
) -> tuple[list[EdlItem], list[PlanNote]]:
    """Snap every item (modes overrides DEFAULT_SNAP per kind); return them
    in time order and notes for the items that had to be dropped because
    even their frame-grid place overlaps another item. An item only moves
    to its snap target when that keeps clear of the items already placed
    and of the frame-grid places of the items still to come. A loop ending
    (edl.is_loop_ending) and the fixed ids (a composite's items) keep their
    frame-grid place."""
    mode_of = {**DEFAULT_SNAP, **(modes or {})}
    ordered = sorted(items, key=lambda i: (i.t_start, i.id))
    reserved = {i.id: _Placed(i.kind, *_frame_place(i, timing)) for i in ordered}
    snapped: list[EdlItem] = []
    notes: list[PlanNote] = []
    for item in ordered:
        own = reserved.pop(item.id)
        options = (
            []
            if is_loop_ending(item) or item.id in fixed
            else [_anchored_place(item, mode_of[item.kind], timing)]
        )
        options.append((own.start, own.end))
        others = list(reserved.values())
        place = next(
            (o for o in options if o and not _conflicts(item.kind, *o, others)), None
        )
        if place is None:
            notes.append(
                PlanNote(
                    item.id,
                    item.kind,
                    "dropped",
                    "on the frame grid it would overlap another item",
                    item.t_start,
                )
            )
            continue
        reserved[item.id] = _Placed(item.kind, *place)
        snapped.append(_at(item, *place, timing.fps))
    return sorted(snapped, key=lambda i: (i.t_start, i.id)), notes


def _covers_punchline(
    start: int, end: int, timing: PlanTiming
) -> tuple[float, float] | None:
    t0, t1 = start / timing.fps, end / timing.fps
    return next(
        (
            (w0, w1)
            for w0, w1 in sorted(timing.punchlines)
            if t0 < w1 - EPSILON and w0 < t1 - EPSILON
        ),
        None,
    )


def protect_punchlines(
    items: Sequence[EdlItem],
    timing: PlanTiming,
    fixed: frozenset[int] = frozenset(),
) -> tuple[list[EdlItem], list[PlanNote]]:
    """Move every SFX (snapped items) that covers a punchline word to end one
    frame before the word starts, its length kept; drop it when it does not
    fit before the word, would cover another punchline or exceed the SFX
    stack, or is fixed (part of a composite). Return the items in time order
    and a note per SFX touched."""
    current = {i.id: i for i in items}
    notes: list[PlanNote] = []
    for item in sorted(items, key=lambda i: (i.t_start, i.id)):
        start = round(item.t_start * timing.fps)
        end = round(item.t_end * timing.fps)
        word = _covers_punchline(start, end, timing) if item.kind == "sfx" else None
        if word is None:
            continue
        new_end = math.floor(word[0] * timing.fps + EPSILON) - 1
        new_start = new_end - (end - start)
        others = [
            _Placed(o.kind, round(o.t_start * timing.fps), round(o.t_end * timing.fps))
            for o in current.values()
            if o.id != item.id
        ]
        fits = (
            item.id not in fixed
            and new_start >= 0
            and _covers_punchline(new_start, new_end, timing) is None
            and not _conflicts("sfx", new_start, new_end, others)
        )
        if fits:
            current[item.id] = _at(item, new_start, new_end, timing.fps)
            reason = (
                f"moved to end one frame before the punchline word at {word[0]:g} s"
            )
            notes.append(PlanNote(item.id, item.kind, "moved", reason, item.t_start))
        else:
            del current[item.id]
            reason = (
                f"it covered the punchline word at {word[0]:g} s and did not "
                "fit before it"
            )
            notes.append(PlanNote(item.id, item.kind, "dropped", reason, item.t_start))
    return sorted(current.values(), key=lambda i: (i.t_start, i.id)), notes
