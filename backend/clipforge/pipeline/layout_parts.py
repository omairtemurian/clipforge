"""The parts that the layout filter graphs (pipeline/layouts) are built of.

A window's left edge (and the fill window's top, if its keyframes set
one) is a crop x (y) expression in t, the seconds since the
clip's start (crop evaluates x at each frame), that moves linearly from
keyframe to keyframe and holds before the first and after the last one:

    x0 + (x1 - x0) * clip((t - t0) / (t1 - t0), 0, 1) + ...

The terms are added as a balanced tree of parenthesized halves, because
ffmpeg refuses (EINVAL) an expression nested more than 100 deep
(libavutil/eval.c MAX_DEPTH), which a flat sum of about 98 terms is.

fit_graph shows the whole frame, scaled to fit inside the output, over a
copy of itself scaled to fill the output and blurred (blurring a
quarter-size copy and scaling it up looks the same and is about 4 times
faster), or over black. square_graph shows a square of the frame (its
shorter side) the same way, scaled to the output's width, its center
following the subject (square_centers), its bottom at SQUARE_BOTTOM of a
portrait output so that lower-third and bottom captions stay below it.
"""

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from itertools import pairwise

from clipforge.models import CropPlan, CropWindow, FitBackground

# The fit background is blurred at 1/BLUR_SCALE of the output size, with a
# box blur of BLUR_RADIUS pixels applied BLUR_POWER times.
BLUR_SCALE = 4
BLUR_RADIUS = 10
BLUR_POWER = 2
# The square of square_graph ends at this share of a portrait output's height.
SQUARE_BOTTOM = 0.66
# square_centers averages the centers of this many keyframes on each side.
SQUARE_SMOOTHING = 5


def ramp_expr(
    times: Sequence[float],
    values: Sequence[float],
    start: float,
    spec: str = "d",
) -> str:
    """Return the expression in t of a value that is values[k] at times[k]
    source seconds, in a clip that starts at start seconds, and moves
    linearly between them (module docstring); numbers are formatted with
    the format spec spec ("d" for ints). values must not be empty."""
    terms = [f"{values[0]:{spec}}"]
    for (t0, v0), (t1, v1) in pairwise(zip(times, values, strict=True)):
        if v1 != v0:
            terms.append(
                f"{v1 - v0:+{spec}}*clip((t{start - t0:+.3f})/{t1 - t0:.3f},0,1)"
            )
    return balanced_sum(terms)


def window_x(times: Sequence[float], xs: Sequence[int], start: float) -> str:
    """Return the crop x expression of a window whose left edge is xs[k] at
    times[k] source seconds, in a clip that starts at start seconds; the
    window is centered if there are no keyframes."""
    if not xs:
        return "(iw-ow)/2"
    return ramp_expr(times, xs, start)


def crop_window(plan: CropPlan, window: CropWindow | None, start: float) -> str:
    """Return the crop filter of window of plan (its fill window if None)
    for a clip that starts at start seconds. The fill window's top moves
    like its left edge if its keyframes set one (else it is plan.y)."""
    times = [keyframe.t for keyframe in plan.keyframes]
    if window is None:
        xs = [keyframe.x for keyframe in plan.keyframes]
        width, height, y = plan.width, plan.height, str(plan.y)
        if any(keyframe.y is not None for keyframe in plan.keyframes):
            ys = [plan.y if k.y is None else k.y for k in plan.keyframes]
            y = f"'{window_x(times, ys, start)}'"
    else:
        xs, width, height = window.xs, window.width, window.height
        y = str(window.y)
    return f"crop=w={width}:h={height}:x='{window_x(times, xs, start)}':y={y}"


def plan_span(plan: CropPlan, start: float, end: float) -> CropPlan:
    """Return plan with only the keyframes (and window xs) that frame start
    to end seconds of the source: from the last keyframe at or before start
    to the first at or after end, and SQUARE_SMOOTHING more on each side
    for square_centers. The crop expressions of the result are the same
    from start to end (they hold outside their keyframes), but a scene of a
    long clip no longer carries every keyframe of the clip (steering: long
    clip render)."""
    times = [keyframe.t for keyframe in plan.keyframes]
    first = max(bisect_right(times, start) - 1 - SQUARE_SMOOTHING, 0)
    last = min(bisect_left(times, end) + 1 + SQUARE_SMOOTHING, len(times))
    if first == 0 and last == len(times):
        return plan

    def cut(window: CropWindow) -> CropWindow:
        if len(window.xs) != len(times):
            return window
        return window.model_copy(update={"xs": window.xs[first:last]})

    top, bottom = plan.split
    return plan.model_copy(
        update={
            "keyframes": plan.keyframes[first:last],
            "split": (cut(top), cut(bottom)),
            "grid": [cut(window) for window in plan.grid],
            "inset": None if plan.inset is None else cut(plan.inset),
        }
    )


def fit_graph(
    head: str,
    size: tuple[int, int],
    background: FitBackground,
    out: str,
    tag: str = "",
) -> str:
    """Return the graph that fits the frames of the filter chain head into
    size (width, height) over background (module docstring), written to the
    stream label out; tag is added to the labels inside the graph."""
    width, height = size
    front = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
        "force_divisible_by=2"
    )
    return over_background(head, size, background, front, None, out, tag)


def square_graph(
    plan: CropPlan,
    start: float,
    size: tuple[int, int],
    head: str,
    out: str,
    tag: str,
) -> str:
    """Return the graph of the square_blur layout (module docstring) of the
    clip of plan that starts at start seconds, as size frames of the chain
    head, written to out; tag is added to the labels inside the graph."""
    side = min(size)
    times = [keyframe.t for keyframe in plan.keyframes]
    centers = [round(center) for center in square_centers(plan)]
    x = f"({window_x(times, centers, start)})-ow/2" if centers else "(iw-ow)/2"
    front = (
        f"crop=w='min(iw,ih)':h='min(iw,ih)':x='{x}':y='(ih-oh)/2',scale={side}:{side}"
    )
    return over_background(
        head, size, plan.background, front, square_place(size), out, tag
    )


def square_place(size: tuple[int, int]) -> tuple[int, int]:
    """Return the (left, top) of square_graph's square in a size output:
    centered across; its bottom at SQUARE_BOTTOM of the height, but no lower
    than centered."""
    width, height = size
    side = min(size)
    centered = even((height - side) // 2)
    top = min(centered, max(0, even(round(height * SQUARE_BOTTOM)) - side))
    return even((width - side) // 2), top


def square_centers(plan: CropPlan) -> list[float]:
    """Return the center x, in source pixels, of square_graph's square at
    each keyframe of plan: the middle of the faces and people seen if there
    are two or more, else the fill window's center; averaged over
    SQUARE_SMOOTHING keyframes on each side, so the square glides."""
    raw = []
    for keyframe in plan.keyframes:
        seen = [face for face in keyframe.faces if face.kind != "object"]
        if len(seen) >= 2:
            left = min(face.x for face in seen)
            right = max(face.x + face.width for face in seen)
            raw.append((left + right) / 2)
        else:
            raw.append(keyframe.x + plan.width / 2)
    smoothed = []
    for index in range(len(raw)):
        near = raw[max(0, index - SQUARE_SMOOTHING) : index + SQUARE_SMOOTHING + 1]
        smoothed.append(sum(near) / len(near))
    return smoothed


def over_background(
    head: str,
    size: tuple[int, int],
    background: FitBackground,
    front: str,
    place: tuple[int, int] | None,
    out: str,
    tag: str = "",
) -> str:
    """Return the graph that frames the frames of head with the filters
    front, at place (left, top; None: centered) of a size output, over a
    blurred copy of them scaled to fill it, or over black, written to out."""
    width, height = size
    if background == "black":
        x, y = ("(ow-iw)/2", "(oh-ih)/2") if place is None else place
        return f"{head},{front},pad={width}:{height}:{x}:{y}:black,setsar=1{out}"
    x, y = ("(W-w)/2", "(H-h)/2") if place is None else place
    front_in, back, blurred, fitted = (
        f"[{name}{tag}]" for name in ("front", "back", "blurred", "fitted")
    )
    small = f"{width // BLUR_SCALE}:{height // BLUR_SCALE}"
    return (
        f"{head},split=2{front_in}{back};"
        f"{back}scale={small}:force_original_aspect_ratio=increase,"
        f"crop={small},boxblur=luma_radius={BLUR_RADIUS}:"
        f"luma_power={BLUR_POWER},scale={width}:{height}{blurred};"
        f"{front_in}{front}{fitted};"
        f"{blurred}{fitted}overlay=x={x}:y={y},setsar=1{out}"
    )


def zoomed_side(side: int, scale: str) -> str:
    """Return the expression of a frame side of side pixels scaled by the
    expression scale, rounded down to an even number, never below side: a
    ramp back to 1 can sum to 0.9999999999999999 (1.15 - 0.15), which
    would give side - 2 pixels, and the crop back to side pixels would then
    read past the frame (ffmpeg crashed with SIGBUS, TASK-236)."""
    return f"max({side},2*trunc({side}*({scale})/2))"


def zoom_offset(center: str, scaled: str, side: int) -> str:
    """Return the crop offset (x or y) expression that puts the point center
    (pixels of the unscaled side) at the middle of a side-pixel window of a
    side scaled to scaled pixels, clamped inside it."""
    return f"clip(trunc(({center})*{scaled}/{side}-{side / 2:g}),0,{scaled}-{side})"


def even(value: int) -> int:
    """Round value down to an even number."""
    return value - value % 2


def balanced_sum(terms: Sequence[str]) -> str:
    """Return the sum of terms as (first half)+(second half), recursively,
    so the expression nests about log2(len(terms)) deep."""
    if len(terms) == 1:
        return terms[0]
    half = len(terms) // 2
    return f"({balanced_sum(terms[:half])})+({balanced_sum(terms[half:])})"
