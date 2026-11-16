"""J and L cuts of a Pro Edit render (SPEC-v3 3.3 pacing): at each cut of the
clip (a joint between two played spans, render/base.ProEditBase.cuts) the
sound switches a few frames before (J cut: the next part's sound leads its
picture) or after the picture (L cut: the last part's sound trails over
the next picture), by JL_FRAMES[intensity] frames (2-8).

Every part keeps its sound in sync with its picture: a J cut plays the
next part's sound from frames before its start (sound the clip's cut
removed) instead of the last part's final frames of sound; an L cut plays
the last part's sound on past its end instead of the next part's first
frames of sound. So both the sound added and the sound dropped must hold
no word of the source (the clip's words, cut or not): a J cut is tried
first, then an L cut, then each one frame shorter, down to JL_MIN_FRAMES;
when none is free of words, or the added sound is outside the clip, the
cut stays a straight cut. The sound stays as long as the picture.

Reaction holds (SPEC-v3 3.3 pacing): after each punchline word the picture
holds on the reaction for HOLD_S[intensity] seconds (0.5-1.0): no visual
pattern interrupt that changes the shot (HOLD_KINDS: not a sound, nor a
layer such as a beat shake drawn over the shot) starts after the word's
end frame and before the hold's end. A move that starts by the frame after the word
(the punchline's own reaction, e.g. a payoff or skull), one in a
punchline word, a manual item, a whole-clip look and the loop ending are
exempt. The rule-based Director leaves out moves that would break a hold
(director_build.PlanBuilder); post-processing moves any other such item to
the hold's end, or drops it when it does not fit there (hold_reactions).
"""

from collections.abc import Sequence

from clipforge.models import EdlItem, EdlKind, ProEditIntensity
from clipforge.proedit.budgets import INTERRUPT_KINDS
from clipforge.proedit.composites import is_look
from clipforge.proedit.edl import (
    LAYER_KINDS,
    TRACK_OF_KIND,
    is_loop_ending,
    track_problems,
)
from clipforge.proedit.snap import PlanNote, PlanTiming

Span = tuple[float, float]

JL_FRAMES: dict[ProEditIntensity, int] = {
    "clean": 2,
    "standard": 4,
    "pro": 6,
    "extreme": 8,
}
JL_MIN_FRAMES = 2
HOLD_S: dict[ProEditIntensity, float] = {
    "clean": 1.0,
    "standard": 0.8,
    "pro": 0.6,
    "extreme": 0.5,
}
HOLD_KINDS: frozenset[EdlKind] = INTERRUPT_KINDS - {"sfx"} - LAYER_KINDS
EPSILON = 1e-6


def _clear(span: Span, words: Sequence[Span]) -> bool:
    """Whether no word overlaps span."""
    start, end = span
    return all(end <= w0 + EPSILON or w1 <= start + EPSILON for w0, w1 in words)


def _fits(
    offset: float,
    joint: int,
    spans: Sequence[Span],
    shifts: Sequence[float],
    words: Sequence[Span],
    clip_length: float,
    frame: float,
) -> bool:
    """Whether the sound of the cut after spans[joint] may move by offset
    seconds (< 0: J cut, > 0: L cut), each part's sound keeping at least a
    frame, given the shifts already chosen for the cuts before it."""
    (s0, e0), (s1, e1) = spans[joint], spans[joint + 1]
    before = shifts[joint - 1] if joint > 0 else 0.0
    if e0 + offset - (s0 + before) < frame - EPSILON:
        return False
    if e1 - (s1 + offset) < frame - EPSILON:
        return False
    if offset < 0:
        added, dropped = (s1 + offset, s1), (e0 + offset, e0)
        inside = added[0] >= -EPSILON
    else:
        added, dropped = (e0, e0 + offset), (s1, s1 + offset)
        inside = added[1] <= clip_length + EPSILON
    return inside and _clear(added, words) and _clear(dropped, words)


def jl_shifts(
    spans: Sequence[Span],
    words: Sequence[Span],
    clip_length: float,
    fps: int,
    frames: int,
) -> list[float]:
    """Return how many seconds the sound of each cut between spans (the
    played (start, end) seconds from the clip start, in play order) moves:
    < 0 a J cut, > 0 an L cut, 0 a straight cut (module docstring). words
    are the source's words in seconds from the clip start and clip_length
    the seconds of source the render reads."""
    frame = 1 / fps
    shifts: list[float] = []
    for joint in range(len(spans) - 1):
        chosen = 0.0
        if abs(spans[joint + 1][0] - spans[joint][1]) > EPSILON:
            for count in range(frames, JL_MIN_FRAMES - 1, -1):
                tries = (-count / fps, count / fps)
                found = [
                    offset
                    for offset in tries
                    if _fits(offset, joint, spans, shifts, words, clip_length, frame)
                ]
                if found:
                    chosen = found[0]
                    break
        shifts.append(chosen)
    return shifts


def audio_spans(spans: Sequence[Span], shifts: Sequence[float]) -> list[Span]:
    """Return the spans of source sound that play with the picture spans
    when the sound of each cut between them moves by shifts (jl_shifts)."""
    moved = [0.0, *shifts, 0.0]
    return [
        (start + moved[n], end + moved[n + 1]) for n, (start, end) in enumerate(spans)
    ]


def jl_spans(
    spans: Sequence[Span],
    words: Sequence[Span],
    clip_length: float,
    fps: int,
    frames: int,
) -> list[Span] | None:
    """Return the spans of sound that play with the picture spans with J and
    L cuts of up to frames frames (module docstring); None when every cut
    stays straight (the sound plays the picture's spans)."""
    if frames < JL_MIN_FRAMES or len(spans) < 2:
        return None
    shifts = jl_shifts(spans, words, clip_length, fps, frames)
    if not any(shifts):
        return None
    return audio_spans(spans, shifts)


def reaction_holds(timing: PlanTiming, intensity: ProEditIntensity) -> list[Span]:
    """Return the (start, end) seconds of the reaction hold after each
    punchline word of timing: from the frame after the word's end to
    HOLD_S[intensity] after its end (cut at the clip end)."""
    holds = []
    for _, end in timing.punchlines:
        start, stop = (
            end + 1 / timing.fps,
            min(end + HOLD_S[intensity], timing.duration),
        )
        if stop > start + EPSILON:
            holds.append((start, stop))
    return holds


def broken_hold(
    item: EdlItem, holds: Sequence[Span], timing: PlanTiming
) -> Span | None:
    """Return the hold (reaction_holds) that item would break by starting
    in it (module docstring), None when it breaks none."""
    exempt = (
        item.kind not in HOLD_KINDS
        or item.source == "manual"
        or is_look(item, timing.duration)
        or is_loop_ending(item)
    )
    t = item.t_start
    if exempt or any(w0 - EPSILON <= t < w1 for w0, w1 in timing.punchlines):
        return None
    return next(
        ((a, b) for a, b in holds if a + EPSILON < t < b - EPSILON),
        None,
    )


def hold_reactions(
    items: Sequence[EdlItem],
    timing: PlanTiming,
    intensity: ProEditIntensity,
    exempt: frozenset[int] = frozenset(),
) -> tuple[list[EdlItem], list[PlanNote]]:
    """Move every item that breaks a reaction hold to start at the hold's
    end (frame grid, its length kept), or drop it when it would then pass
    the clip end, break another hold or clash on its track. The exempt ids
    (a composite's items, which only move together) are left as they are.
    Return the items in time order and a note per item touched."""
    holds = reaction_holds(timing, intensity)
    current = {i.id: i for i in items}
    notes: list[PlanNote] = []
    for item in sorted(items, key=lambda i: (i.t_start, i.id)):
        hold = None if item.id in exempt else broken_hold(item, holds, timing)
        if hold is None:
            continue
        start = round(hold[1] * timing.fps)
        end = start + max(1, round((item.t_end - item.t_start) * timing.fps))
        moved = item.model_copy(
            update={"t_start": start / timing.fps, "t_end": end / timing.fps}
        )
        track = TRACK_OF_KIND[item.kind]
        same_track = [
            o
            for o in current.values()
            if o.id != item.id and TRACK_OF_KIND[o.kind] == track
        ]
        fits = (
            end <= timing.last_frame
            and broken_hold(moved, holds, timing) is None
            and not track_problems([*same_track, moved])
        )
        if fits:
            current[item.id] = moved
            reason = f"moved after the reaction hold that ends at {hold[1]:g} s"
            notes.append(PlanNote(item.id, item.kind, "moved", reason, item.t_start))
        else:
            del current[item.id]
            reason = (
                f"it started in the reaction hold from {hold[0]:g} to "
                f"{hold[1]:g} s and did not fit after it"
            )
            notes.append(PlanNote(item.id, item.kind, "dropped", reason, item.t_start))
    return sorted(current.values(), key=lambda i: (i.t_start, i.id)), notes
