"""The video filter graphs of the clip layouts (SPEC 6.8 and 6.11).

Each graph reads the first video stream of input 0, which starts at the
clip's start (input -ss), and writes the clip's frames, of its aspect's
output size at fps frames a second, to [v] (or to the label that render
draws the captions from):

- fill: the crop plan's fill window, which follows the subject, scaled to
  the output size;
- fit: the whole frame, scaled to fit inside the output, over a copy of
  itself scaled to fill the output and blurred (blurring a quarter-size
  copy and scaling it up looks the same and is about 4 times faster), or
  over black if the plan's background is black;
- square_blur: a square of the frame that follows the subject, scaled to
  the output's width, over the same blurred copy (layout_parts.square_graph);
- split: the crop plan's two split windows, each scaled to half the output
  height, stacked top and bottom;
- grid: the crop plan's three grid windows (left, middle and right
  speaker), each scaled to a third of the output (grid_cells): stacked
  top to bottom in a portrait output, side by side left to right in a
  square or landscape one;
- pip: the fill window scaled to the output, with an inset in its top
  right corner (inset_geometry): the plan's inset window, a square on the
  other speaker, or the whole frame fitted in the square if the plan has
  none, with a white border;
- screenshare and gameplay: the video and its facecam, stacked
  (pipeline/facecam).

The windows' crop filters, and the fit graph, are built by
pipeline/layout_parts.
"""

from clipforge.models import CropPlan, Layout
from clipforge.pipeline.facecam import FACECAM_LAYOUTS, facecam_graph
from clipforge.pipeline.layout_parts import (
    crop_window,
    even,
    fit_graph,
    square_graph,
)

# The video stream a graph reads and the stream it writes.
VIDEO_IN = "[0:V:0]"
VIDEO_OUT = "[v]"
# The pip inset is a square INSET_SHARE of the output's shorter side, with a
# white border of 1/INSET_BORDER of that side, INSET_MARGIN of it from the
# top and right edges.
INSET_SHARE = 0.36
INSET_BORDER = 180
INSET_MARGIN = 0.04
# The layouts that need the windows of pipeline/layout_windows in the plan.
WINDOW_LAYOUTS: tuple[Layout, ...] = ("grid", "pip")


def grid_cells(size: tuple[int, int]) -> list[tuple[int, int]]:
    """Return the (width, height) of the three cells of the grid layout in
    a size (width, height) output: rows if it is taller than wide, else
    columns; each an even third, the last taking what is left."""
    width, height = size
    if height > width:
        third = even(height // 3)
        return [(width, third), (width, third), (width, height - 2 * third)]
    third = even(width // 3)
    return [(third, height), (third, height), (width - 2 * third, height)]


def inset_geometry(size: tuple[int, int]) -> tuple[int, int, int]:
    """Return the side of the pip inset's square, its border and its margin
    from the output's top and right edges, in pixels of a size output, all
    even."""
    short = min(size)
    side = max(2, even(round(short * INSET_SHARE)))
    border = max(2, even(short // INSET_BORDER))
    margin = even(round(short * INSET_MARGIN))
    return side, border, margin


def nudge_plan(plan: CropPlan, offset: float) -> CropPlan:
    """Return plan with its fill window shifted right by offset times the
    window's width (left if negative), to even pixels as yuv420p needs. The
    window never goes left of the frame; crop keeps it inside on the right."""
    shift = round(offset * plan.width / 2) * 2
    if shift == 0:
        return plan
    keyframes = [
        keyframe.model_copy(update={"x": max(keyframe.x + shift, 0)})
        for keyframe in plan.keyframes
    ]
    return plan.model_copy(update={"keyframes": keyframes})


def layout_graph(
    plan: CropPlan,
    layout: Layout,
    start: float,
    size: tuple[int, int],
    fps: int,
    out: str = VIDEO_OUT,
    *,
    head: str | None = None,
    tag: str = "",
) -> str:
    """Return the -filter_complex graph that frames, in layout, the clip of
    plan that starts at start seconds, as size (width, height) frames at fps
    frames a second, written to the stream label out.

    The graph reads VIDEO_IN at fps, or the frames of the filter chain head
    if set (a scene's, pipeline/scene_graph); tag is added to the labels
    inside the graph, so that graphs with different tags can be joined."""
    width, height = size
    head = f"{VIDEO_IN}fps={fps}" if head is None else head
    upper, lower, top_out, bottom_out = (
        f"[{name}{tag}]" for name in ("upper", "lower", "top", "bottom")
    )
    if layout == "fill":
        fill = crop_window(plan, None, start)
        return f"{head},{fill},scale={width}:{height},setsar=1{out}"
    if layout == "fit":
        return fit_graph(head, size, plan.background, out, tag)
    if layout == "square_blur":
        return square_graph(plan, start, size, head, out, tag)
    if layout in FACECAM_LAYOUTS:
        return facecam_graph(plan, layout, size, head, out, tag)
    if layout == "grid":
        return grid_graph(plan, start, size, head, out, tag)
    if layout == "pip":
        return pip_graph(plan, start, size, head, out, tag)
    top, bottom = (crop_window(plan, window, start) for window in plan.split)
    half = f"scale={width}:{height // 2}"
    return (
        f"{head},split=2{upper}{lower};"
        f"{upper}{top},{half}{top_out};{lower}{bottom},{half}{bottom_out};"
        f"{top_out}{bottom_out}vstack=inputs=2,setsar=1{out}"
    )


def grid_graph(
    plan: CropPlan,
    start: float,
    size: tuple[int, int],
    head: str,
    out: str,
    tag: str,
) -> str:
    """Return the graph of the grid layout (layout_graph's arguments): each
    of plan's three grid windows scaled to its grid cell, stacked. Raises
    ValueError if plan has no grid windows (layout_windows adds them)."""
    if len(plan.grid) != 3:
        raise ValueError("the crop plan has no grid windows")
    width, height = size
    cells = grid_cells(size)
    ins = [f"[cell{n}{tag}]" for n in range(3)]
    outs = [f"[celled{n}{tag}]" for n in range(3)]
    parts = [f"{head},split=3{''.join(ins)}"]
    for label, window, (cell_w, cell_h), framed in zip(
        ins, plan.grid, cells, outs, strict=True
    ):
        crop = crop_window(plan, window, start)
        parts.append(f"{label}{crop},scale={cell_w}:{cell_h},setsar=1{framed}")
    stack = "vstack" if height > width else "hstack"
    parts.append(f"{''.join(outs)}{stack}=inputs=3,setsar=1{out}")
    return ";".join(parts)


def pip_graph(
    plan: CropPlan,
    start: float,
    size: tuple[int, int],
    head: str,
    out: str,
    tag: str,
) -> str:
    """Return the graph of the pip layout (layout_graph's arguments): the
    fill window scaled to size, with the inset (plan's inset window, else
    the whole frame) bordered in white over its top right corner."""
    width, height = size
    side, border, margin = inset_geometry(size)
    main, small, base, corner = (
        f"[{name}{tag}]" for name in ("pipmain", "pipsmall", "pipbase", "pipcorner")
    )
    if plan.inset is None:
        inset = (
            f"scale={side}:{side}:force_original_aspect_ratio=decrease:"
            "force_divisible_by=2"
        )
    else:
        inset = f"{crop_window(plan, plan.inset, start)},scale={side}:{side}"
    fill = crop_window(plan, None, start)
    return (
        f"{head},split=2{main}{small};"
        f"{main}{fill},scale={width}:{height},setsar=1{base};"
        f"{small}{inset},setsar=1,pad=w=iw+{2 * border}:h=ih+{2 * border}:"
        f"x={border}:y={border}:color=white{corner};"
        f"{base}{corner}overlay=x=W-w-{margin}:y={margin},setsar=1{out}"
    )
