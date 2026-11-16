"""Transitions of a Pro Edit render (SPEC-v3 3.3): the fx track's transition
items, joined as the normal render joins its transitions
(pipeline/transitions.py, SPEC-v2 3.5).

Each transition is drawn on its window only (window.over_window), so
frames outside the windows pass through bit for bit (xfade blends in
444/RGB formats only, which would resample the chroma of every frame) and
the clip keeps its length and every later item its time. The window's
frames (`trim`) are split at its middle frame (cut) into the part before
and the part after, and transitions.join_graph joins the two with an
`xfade` over the whole window: the part before is padded with copies of
its last frame and the part after with copies of its first, half the
window each. A window of an odd number of frames ends on the part after's
last frame unblended; one of a single frame is not drawn (nothing to
blend). Windows of the fx track never overlap (edl.py).

The xfade of each type: crossfade, whip and zoom are the normal render's
crossfade, whip and zoom_punch (transitions.XFADE: fade, hblur, zoomin);
flash fades through white (fadewhite); glitch pixelizes (pixelize) and the
glitch stage (fx_glitch) draws glitch frames on its window; a loop
transition (the loop-friendly ending) is drawn by loop_end.py instead. A
transition's whoosh is a sound, placed by the SFX engine; the picture does
not read it.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial

from clipforge.pipeline.transitions import XFADE, Join, join_graph
from clipforge.proedit.edl import TransitionItem, TypedEdlItem
from clipforge.proedit.render.timing import frame_range
from clipforge.proedit.render.window import over_window, window_frames

XFADE_OF_TYPE: dict[str, str] = {
    "crossfade": XFADE["crossfade"],
    "whip": XFADE["whip"],
    "zoom": XFADE["zoom_punch"],
    "flash": "fadewhite",
    "glitch": "pixelize",
}
LABELS = "pe_tr"


@dataclass(frozen=True)
class TransitionWindow:
    """The frames of a transition at a frame rate: first..end-1 (from 0),
    cut after the first half frames and blended by join."""

    first: int
    end: int
    half: int
    join: Join

    @property
    def cut(self) -> int:
        """Return the first frame of the part after the cut."""
        return self.first + self.half


def transition_items(items: Sequence[TypedEdlItem]) -> list[TransitionItem]:
    """Return the transition items of items that blend two parts of the
    clip, in time order (a loop ending is drawn by loop_end.py)."""
    found = [
        item
        for item in items
        if isinstance(item, TransitionItem) and item.params.type != "loop"
    ]
    return sorted(found, key=lambda item: (item.t_start, item.id))


def transition_windows(
    items: Sequence[TypedEdlItem], fps: int
) -> list[TransitionWindow]:
    """Return the window of each transition among items that holds at least
    two frames at fps, in time order."""
    windows = []
    for item in transition_items(items):
        first, end = frame_range(item.t_start, item.t_end, fps)
        half = (end - first) // 2
        if half >= 1:
            join = Join(XFADE_OF_TYPE[item.params.type], half, half / fps)
            windows.append(TransitionWindow(first, end, half, join))
    return windows


def blend_branch(window: TransitionWindow, fps: int, name: str, source: str) -> str:
    """Return the chain that makes the blended frames of window from source,
    the label of a copy of the stream at fps, ending unlabeled (module doc);
    name keeps its labels apart."""

    def frames_of(first: int, end: int, label: str) -> str:
        return f"[{name}_{label}]{window_frames('', first, end)}[{name}_{label}p]"

    parts = (
        f"{source}split[{name}_a][{name}_b];"
        f"{frames_of(window.first, window.cut, 'a')};"
        f"{frames_of(window.cut, window.end, 'b')}"
    )
    spans = [(0.0, window.half / fps), (window.half / fps, math.inf)]
    pieces = [f"[{name}_ap]", f"[{name}_bp]"]
    return f"{parts};{join_graph(pieces, spans, [window.join], '', name)}"


def transition_filters(items: Sequence[TypedEdlItem], fps: int) -> list[str]:
    """Return the filters that draw the transition items among items at fps
    (module doc), in time order; none without transitions."""
    filters = []
    for index, window in enumerate(transition_windows(items, fps)):
        name = f"{LABELS}{index}"
        branch = partial(blend_branch, window, fps, name)
        filters.append(over_window(name, window.first, window.end, fps, branch))
    return filters
