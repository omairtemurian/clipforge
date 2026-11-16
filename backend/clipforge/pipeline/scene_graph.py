"""The video filter graph of a clip framed scene by scene (STEERING item 7).

A clip whose scenes are framed differently (pipeline/scene_framing) is
rendered as its scenes' parts, each with its own crop plan and layout:
the clip's frames, at fps, are split once per part; each part keeps its
own frames (trim, by time since the clip's start, starting again at 0;
the first part from the clip's first frame, the last to its last)
and frames them in its layout (layouts.layout_graph, whose crop
expressions then count t from the part's start, with only the keyframes
around the part: layout_parts.plan_span); concat joins the parts
back together in order. trim keeps the frames from its start up to, not
including, its end, so each frame is in exactly one part and nothing is
interpolated across a scene's edge. A zoomed-out part with an ease in
or out zooms from or to its fill neighbour (pipeline/zoom_transition).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from clipforge.models import CropPlan, Layout
from clipforge.pipeline.layout_parts import plan_span
from clipforge.pipeline.layouts import VIDEO_IN, VIDEO_OUT, layout_graph
from clipforge.pipeline.zoom_transition import Ease, transition_filter


@dataclass(frozen=True)
class ScenePart:
    """start to end seconds of the source framed in layout with plan;
    ease_in and ease_out zoom from and to a fill neighbour."""

    start: float
    end: float
    plan: CropPlan
    layout: Layout
    ease_in: Ease | None = None
    ease_out: Ease | None = None


def scene_graph(
    parts: Sequence[ScenePart],
    start: float,
    size: tuple[int, int],
    fps: int,
    out: str = VIDEO_OUT,
) -> str:
    """Return the graph that frames each of parts (in order, covering the
    clip that starts at start seconds) in its layout with its plan, as size
    (width, height) frames at fps frames a second, and joins them into the
    stream label out (module docstring)."""
    count = len(parts)
    inputs = "".join(f"[scene{index}]" for index in range(count))
    graph = [f"{VIDEO_IN}fps={fps},split={count}{inputs}"]
    for index, part in enumerate(parts):
        bounds = []
        if index > 0:
            bounds.append(f"start={part.start - start:.6f}")
        if index < count - 1:
            bounds.append(f"end={part.end - start:.6f}")
        head = f"[scene{index}]trim={':'.join(bounds)},setpts=PTS-STARTPTS"
        ease = transition_filter(
            part.layout,
            part.plan,
            (part.start, part.end),
            (part.ease_in, part.ease_out),
            size,
        )
        framed = f"[wide{index}]" if ease else f"[framed{index}]"
        graph.append(
            layout_graph(
                plan_span(part.plan, part.start, part.end),
                part.layout,
                part.start,
                size,
                fps,
                out=framed,
                head=head,
                tag=str(index),
            )
        )
        if ease:
            graph.append(f"{framed}{ease}[framed{index}]")
    framed = "".join(f"[framed{index}]" for index in range(count))
    graph.append(f"{framed}concat=n={count}:v=1:a=0{out}")
    return ";".join(graph)
