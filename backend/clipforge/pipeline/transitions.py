"""Transitions at the cuts of a clip's render (SPEC-v2 3.5): crossfade,
zoom punch, whip and slide, auto on jump cuts and manual between sections.

A clip's render plays parts of the source one after another
(sections.played_spans); between two parts is a cut. A cut inside a
section (one of its cut ranges: a jump cut, the auto cut's too) gets the
clip's auto transition, the cut from one section to the next the one the
owner picked for it (models.ClipTransitions; clip_joins).

Each transition is an ffmpeg xfade (XFADE; names checked with
`ffmpeg -h filter=xfade`, ffmpeg 9.0.2) centred on the cut: the part
before it is padded with copies of its last frame and the part after with
copies of its first frame (tpad clone), half the transition each, and
xfade blends the two over the padded window (join_graph). The render
lasts exactly as long as without the transitions, so the captions, the
timeline's layers and the sound (which stays a hard cut) keep their times.
A transition is cut to whole frames and to half of each part it touches,
so neighbouring transitions never overlap.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from clipforge.models import (
    ClipTransitions,
    CutRange,
    SourceSpan,
    Transition,
    TransitionKind,
)
from clipforge.pipeline.frame_cuts import kept_spans
from clipforge.pipeline.sections import Part, section_parts, with_gaps

# The xfade transition of each kind (SPEC-v2 3.5): fade blends the frames,
# zoomin zooms into the part before while it fades, hblur blurs it
# sideways like a whip pan, slideleft pushes it out to the left.
XFADE: dict[TransitionKind, str] = {
    "crossfade": "fade",
    "zoom_punch": "zoomin",
    "whip": "hblur",
    "slide": "slideleft",
}


@dataclass(frozen=True)
class Join:
    """A transition at a cut, as the render makes it: xfade's transition,
    over frames frames on each side of the cut (half seconds)."""

    xfade: str
    frames: int
    half: float


def clip_joins(
    start: float,
    end: float,
    segments: Sequence[SourceSpan],
    cut_ranges: Sequence[CutRange],
    transitions: ClipTransitions,
    fps: int,
) -> list[Join | None]:
    """Return the transition at each cut of the render of the clip from start
    to end that plays segments without cut_ranges at fps, in play order
    (one fewer than sections.played_spans gives parts); None for a hard
    cut.

    A cut inside a section gets transitions.auto; the cut after section i
    (the last section before it that plays anything) gets
    transitions.sections[i] if there is one. Each is fitted to its parts
    (fit_join).
    """
    kept = kept_spans(start, end, with_gaps(cut_ranges, segments), fps)
    wanted: list[Transition | None] = []
    parts: list[Part] = []
    before: int | None = None
    for index, inside in enumerate(section_parts(kept, start, end, segments, fps)):
        if not inside:
            continue
        if before is not None:
            wanted.append(_section_transition(transitions, before))
        wanted += [transitions.auto] * (len(inside) - 1)
        parts += inside
        before = index
    return [
        fit_join(transition, parts[n], parts[n + 1], fps)
        for n, transition in enumerate(wanted)
    ]


def fit_join(
    transition: Transition | None, left: Part, right: Part, fps: int
) -> Join | None:
    """Return transition at the cut between the parts left and right
    ((start, end) seconds) at fps: half its duration on each side, in whole
    frames, and no more than half of either part; None if there is no
    transition or not a frame of it is left."""
    if transition is None:
        return None
    frames = min(
        round(transition.duration * fps / 2),
        _frames(left, fps) // 2,
        _frames(right, fps) // 2,
    )
    if frames < 1:
        return None
    return Join(XFADE[transition.kind], frames, frames / fps)


def has_joins(joins: Sequence[Join | None]) -> bool:
    """Return whether any cut of joins has a transition."""
    return any(join is not None for join in joins)


def join_graph(
    pieces: Sequence[str],
    spans: Sequence[Part],
    joins: Sequence[Join | None],
    out: str,
    prefix: str = "join",
) -> str:
    """Return the filters that join the video pieces, labels of the parts
    spans ((start, end) seconds of the clip, in play order) each starting
    at 0, into out with the transitions joins (one per cut; clip_joins).
    The labels in between start with prefix, so graphs with several joins
    can keep them apart; an empty out leaves the joined stream unlabeled,
    so a filter chain can go on after it (the end of the last span is not
    read).

    Every piece is set to the same time base (settb=AVTB, which xfade
    needs on both inputs) and padded at each end that a transition touches
    with copies of its first or last frame (tpad clone). Then the pieces are
    joined one by one: by concat at a hard cut, by xfade at a transition,
    starting half the transition before the cut.
    """
    if len(joins) != len(pieces) - 1 or len(spans) != len(pieces):
        raise ValueError("join_graph needs a join for each cut between pieces")
    parts: list[str] = []
    for n, piece in enumerate(pieces):
        lead = joins[n - 1] if n > 0 else None
        tail = joins[n] if n < len(joins) else None
        pad = [f"start_mode=clone:start={lead.frames}"] if lead else []
        pad += [f"stop_mode=clone:stop={tail.frames}"] if tail else []
        filters = "settb=AVTB" + (f",tpad={':'.join(pad)}" if pad else "")
        parts.append(f"{piece}{filters}[{prefix}_p{n}]")
    current, cut_at = f"[{prefix}_p0]", 0.0
    for n, join in enumerate(joins):
        cut_at += spans[n][1] - spans[n][0]
        target = out if n == len(joins) - 1 else f"[{prefix}_x{n}]"
        if join is None:
            parts.append(f"{current}[{prefix}_p{n + 1}]concat=n=2:v=1:a=0{target}")
        else:
            parts.append(
                f"{current}[{prefix}_p{n + 1}]xfade=transition={join.xfade}"
                f":duration={2 * join.half:.6f}:offset={cut_at - join.half:.6f}"
                f"{target}"
            )
        current = target
    return ";".join(parts)


def _section_transition(transitions: ClipTransitions, index: int) -> Transition | None:
    """Return the transition after section index; None if none is set."""
    if index < len(transitions.sections):
        return transitions.sections[index]
    return None


def _frames(part: Part, fps: int) -> int:
    """Return how many whole frames at fps the part ((start, end) seconds)
    holds."""
    return math.floor((part[1] - part[0]) * fps + 1e-6)
