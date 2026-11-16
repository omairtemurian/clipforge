"""The loop-friendly ending of a Pro Edit render (SPEC-v3 3.3): a transition
item of type "loop" over the clip's last frames (proedit/retention.py
places it over the last LOOP_S seconds).

Picture: on the item's window (window.over_window, so every other frame
passes through untouched) each frame is blended into the clip's first
frame as the stages drew it (graded, captioned), linearly, the window's
last frame being the first frame itself: the replay starts on the frame
the clip ended on. The blend reads the window frame's time (T): ffmpeg
9.0.2's blend counts N from 1, not 0. This stage runs after every other
one (graph.STAGES), so the ending lands on the finished first frame.

Sound: over the same window the program sound (dialogue, SFX, music and
audio effects, before the master loudness) fades out linearly while its
opening, the same length from the clip start, fades in (an equal-gain
crossfade), so the end sounds like the start the replay begins with.
"""

from collections.abc import Sequence

from clipforge.proedit.edl import TransitionItem, TypedEdlItem
from clipforge.proedit.render.canvas import Canvas
from clipforge.proedit.render.fx_basic import number
from clipforge.proedit.render.timing import frame_range
from clipforge.proedit.render.window import over_window, window_frames

LABELS = "pe_loop"


def loop_item(items: Sequence[TypedEdlItem]) -> TransitionItem | None:
    """Return the loop ending among items (the last one), or None."""
    loops = [
        item
        for item in items
        if isinstance(item, TransitionItem) and item.params.type == "loop"
    ]
    return max(loops, key=lambda item: item.t_end, default=None)


def loop_filters(items: Sequence[TypedEdlItem], canvas: Canvas) -> list[str]:
    """Return the filter that blends the loop ending's window into the
    clip's first frame (module docstring); none without a loop ending."""
    item = loop_item(items)
    if item is None:
        return []
    fps = canvas.fps
    first, end = frame_range(item.t_start, item.t_end, fps)
    count = end - first
    if count < 1:
        return []

    def branch(source: str) -> str:
        start, window, a, b = (f"[{LABELS}_{part}]" for part in ("0", "w", "a", "b"))
        alpha = f"min(1,(round(T*{fps})+1)/{count})"
        return (
            f"{source}split{a}{b};"
            f"{b}trim=end_frame=1,loop=loop={count - 1}:size=1,"
            f"setpts=N/({fps}*TB){start};"
            f"{window_frames(a, first, end)}{window};"
            f"{window}{start}blend=all_expr='A+(B-A)*{alpha}'"
        )

    return [over_window(LABELS, first, end, fps, branch)]


def loop_sound(items: Sequence[TypedEdlItem], fps: int) -> str:
    """Return the audio filters (a chain from one input to one output, as a
    sound_graph stage writes them between labels) that crossfade the sound
    into its opening over the loop ending (module docstring); "" without
    a loop ending."""
    item = loop_item(items)
    if item is None:
        return ""
    first, end = frame_range(item.t_start, item.t_end, fps)
    if end <= first:
        return ""
    start, length = first / fps, (end - first) / fps
    main, head, faded, opening = (
        f"[{LABELS}_{part}]" for part in ("m", "h", "mf", "hf")
    )
    return (
        f"asplit=2{main}{head};"
        f"{head}atrim=end={number(length)},asetpts=N/SR/TB,"
        f"afade=t=in:d={number(length)}:curve=tri,"
        f"adelay=delays={number(start * 1000)}:all=1,asetpts=N/SR/TB{opening};"
        f"{main}afade=t=out:st={number(start)}:d={number(length)}:curve=tri{faded};"
        f"{faded}{opening}amix=inputs=2:duration=first:normalize=0"
    )
