"""Shake, speed ramps and slow motion of a Pro Edit render (SPEC-v3 3.3
pacing): the fx track's shake, speed_ramp and slowmo items.

Shake is drawn by the zoom stage (graph.STAGES "motion"): each frame of a
shake window gets a camera (motion.Camera) that moves the picture by up to
strength * SHAKE_MAX frame widths to and fro, on top of the zoom or pan of
that frame (the frame itself when none). The picture is zoomed in by at
least the room the shift needs (1 + 2 * amplitude, on the tighter axis), so
no border shows, and the window still keeps the subject's face in
(motion.safe_axis). The path is seeded (params.seed): knots every half
period of params.frequency_hz alternate in sign with random sizes of
KNOT_MIN..1 of the amplitude (the vertical path at Y_SHARE of it, half a
knot later) and frames ease between them (cosine), so the same item always
shakes the same way. After t_end the picture snaps back.

Speed ramps and slow motion are their own stage (graph.STAGES "time"),
before freeze frames. Frame k of the count frames of an item's window
shows the clip at content(k) seconds after t_start, where content(0) = 0
and each frame adds its speed / fps:
- speed_ramp: speed_from to speed_to over the window on the item's easing
  curve (easing.ease);
- slowmo: from 1 down to params.speed over the first ramp_s seconds and
  back up over the last (ease_in_out; each ramp at most half the window).
Speeds stay within SPEED_MIN..SPEED_MAX (an elastic curve could overshoot
below 0). At t_end the video snaps back to the clip's own time: a slow
window skips the part of the clip it did not reach, a fast one shows
again what it ran ahead to. The sound is not changed, so it stays in sync
and is in sync again from the first frame after the window; the clip's
length and the times of all other items do not change (docs/decisions.md).

Filters (ffmpeg 9.0.2, verified with `ffmpeg -h filter=<name>` and test
renders; docs/decisions.md): the stream is split; one copy is cut to the
content frames the window needs (`trim` start_frame/end_frame), given the
time at which each one plays (`settb` 1/1000000, `setpts` steps in N, the
frame count), filled in at the clip's frame rate by motion-compensated
interpolation (`minterpolate` mi_mode=mci, which places its frames by
their timestamps), cut to the window's frame count, and delayed to the
window by `tpad` start frames (generated frames, so the other copy never
waits on it: a plain delay buffered every frame before the window, 2.6 GB
for a window at 25 s of 1080p vs 0.24 GB), then drawn over the other copy
on the window's frames (`overlay` enable, eof_action=pass).
"""

import math
import random
from collections.abc import Sequence

from clipforge.models import EdlKind
from clipforge.pipeline.layout_parts import balanced_sum
from clipforge.proedit.edl import ShakeItem, SlowmoItem, SpeedRampItem, TypedEdlItem
from clipforge.proedit.render import motion
from clipforge.proedit.render.canvas import Camera, Canvas
from clipforge.proedit.render.easing import ease
from clipforge.proedit.render.timing import enable, frame_range

SHAKE_KINDS: frozenset[EdlKind] = frozenset({"shake"})
TIME_KINDS: frozenset[EdlKind] = frozenset({"speed_ramp", "slowmo"})
SHAKE_MAX = 0.04
KNOT_MIN = 0.5
Y_SHARE = 0.6
SPEED_MIN = 0.1
SPEED_MAX = 4.0
TIME_BASE = 1_000_000
INTERPOLATION = "mi_mode=mci"
LOOKAHEAD = 4
TimeItem = SpeedRampItem | SlowmoItem


def shake_items(items: Sequence[TypedEdlItem]) -> list[ShakeItem]:
    """Return the shake items of items, in time order."""
    found = [item for item in items if isinstance(item, ShakeItem)]
    return sorted(found, key=lambda item: (item.t_start, item.id))


def shake_path(item: ShakeItem, fps: int) -> dict[int, tuple[float, float]]:
    """Return the shift (x, y) in frame widths of the picture on each frame
    of item's window at fps, by frame number (module docstring)."""
    first, end = frame_range(item.t_start, item.t_end, fps)
    amplitude = item.params.strength * SHAKE_MAX
    knot_s = 1 / (2 * item.params.frequency_hz)
    knots = math.ceil((end - first) / fps / knot_s) + 3
    rng = random.Random(item.params.seed)
    xs = [(-1) ** k * rng.uniform(KNOT_MIN, 1) for k in range(knots)]
    ys = [(-1) ** (k + 1) * rng.uniform(KNOT_MIN, 1) * Y_SHARE for k in range(knots)]
    return {
        frame: (
            amplitude * _between(xs, (frame - first) / fps / knot_s),
            amplitude * _between(ys, (frame - first) / fps / knot_s + 0.5),
        )
        for frame in range(first, end)
    }


def _between(knots: Sequence[float], at: float) -> float:
    """Return the value at at (in knots) eased (cosine) between knots."""
    index = min(int(at), len(knots) - 2)
    share = (1 - math.cos(math.pi * (at - index))) / 2
    return knots[index] + (knots[index + 1] - knots[index]) * share


def shaken(
    cameras: dict[int, Camera], items: Sequence[TypedEdlItem], canvas: Canvas
) -> dict[int, Camera]:
    """Return cameras (by frame number) with the shake items of items drawn
    on them (module docstring)."""
    width, height = canvas.size
    aspect = width / height
    found = dict(cameras)
    for item in shake_items(items):
        amplitude = item.params.strength * SHAKE_MAX
        room = 1 + 2 * amplitude * max(1.0, aspect)
        for frame, (dx, dy) in shake_path(item, canvas.fps).items():
            base = cameras.get(frame, Camera(1.0, *motion.CENTER))
            scale = max(base.scale, room)
            face = canvas.face(frame)
            across = (face.left, face.right) if face else None
            down = (face.top, face.bottom) if face else None
            found[frame] = Camera(
                scale=scale,
                x=motion.safe_axis(base.x + dx / scale, scale, across),
                y=motion.safe_axis(base.y + dy * aspect / scale, scale, down),
            )
    return found


def camera_filters(items: Sequence[TypedEdlItem], canvas: Canvas) -> list[str]:
    """Return the filters that zoom, pan and shake canvas's frames as the
    zoom, pan and shake items of items say; [] if there are none."""
    cameras = shaken(motion.cameras_of(items, canvas), items, canvas)
    return motion.crop_filters(motion.camera_crops(cameras, canvas.size), canvas)


def speeds(item: TimeItem, count: int, fps: int) -> list[float]:
    """Return the speed of each of the count frames of item's window at fps
    (module docstring), taken at the middle of each frame."""
    found = []
    for k in range(count):
        p = (k + 0.5) / count
        if isinstance(item, SpeedRampItem):
            params = item.params
            share = ease(params.ease, p)
            speed = params.speed_from + (params.speed_to - params.speed_from) * share
        else:
            ramp = min(item.params.ramp_s * fps / count, 0.5)
            share = (
                min(ease("ease_in_out", p / ramp), ease("ease_in_out", (1 - p) / ramp))
                if ramp > 0
                else 1.0
            )
            speed = 1 + (item.params.speed - 1) * share
        found.append(min(max(speed, SPEED_MIN), SPEED_MAX))
    return found


def content_times(item: TimeItem, fps: int) -> list[float]:
    """Return content(k) (module docstring) of each frame k of item's
    window at fps, and after them where the window would go on (count + 1
    values)."""
    first, end = frame_range(item.t_start, item.t_end, fps)
    times = [0.0]
    for speed in speeds(item, end - first, fps):
        times.append(times[-1] + speed / fps)
    return times


def content_frames(items: Sequence[TypedEdlItem], fps: int) -> dict[int, float]:
    """Return, for each frame of the windows of the speed_ramp and slowmo
    items of items, the frame number (with its fraction) of the clip it
    shows."""
    shown: dict[int, float] = {}
    for item in time_items(items):
        first, _ = frame_range(item.t_start, item.t_end, fps)
        for k, content in enumerate(content_times(item, fps)[:-1]):
            shown[first + k] = first + content * fps
    return shown


def play_times(times: Sequence[float], fps: int, inputs: int) -> list[float]:
    """Return the second after the window's start at which each of the
    first inputs frames of the clip from the window's first plays, where
    times are content_times; past the window at its last speed."""
    found = []
    last_speed = (times[-1] - times[-2]) * fps
    for index in range(inputs):
        content = index / fps
        k = next((k for k in range(len(times) - 1) if content < times[k + 1]), None)
        if k is None:
            frames = len(times) - 1 + (content - times[-1]) * fps / last_speed
        else:
            frames = k + (content - times[k]) / (times[k + 1] - times[k])
        found.append(frames / fps)
    return found


def time_items(items: Sequence[TypedEdlItem]) -> list[TimeItem]:
    """Return the speed_ramp and slowmo items of items, in time order."""
    found = [item for item in items if isinstance(item, SpeedRampItem | SlowmoItem)]
    return sorted(found, key=lambda item: (item.t_start, item.id))


def pts_steps(times: Sequence[float]) -> str:
    """Return the setpts expression (in 1 / TIME_BASE seconds) that is
    times[N] seconds on frame N."""
    ticks = [round(time * TIME_BASE) for time in times]
    terms = [str(ticks[0])]
    terms += [
        f"{ticks[n] - ticks[n - 1]}*gte(N,{n})"
        for n in range(1, len(ticks))
        if ticks[n] != ticks[n - 1]
    ]
    return balanced_sum(terms)


def time_filters(items: Sequence[TypedEdlItem], fps: int) -> list[str]:
    """Return the filters that play the windows of the speed_ramp and slowmo
    items of items at their speeds (module docstring), at fps."""
    filters = []
    for index, item in enumerate(time_items(items)):
        first, end = frame_range(item.t_start, item.t_end, fps)
        if end <= first:
            continue
        times = content_times(item, fps)
        # One frame past the last needed, so the last frame interpolates.
        inputs = math.ceil(round(times[-1] * fps, 6)) + LOOKAHEAD
        played = play_times(times, fps, inputs)
        main, source, window = (
            f"[pe_time{name}{index}]" for name in ("main", "src", "win")
        )
        filters.append(
            f"split{main}{source};{source}"
            f"trim=start_frame={first}:end_frame={first + inputs},"
            f"settb=1/{TIME_BASE},setpts='{pts_steps(played)}',"
            f"minterpolate=fps={fps}:{INTERPOLATION},"
            f"trim=end_frame={end - first},tpad=start={first}{window};"
            f"{main}{window}overlay=eof_action=pass:repeatlast=0:"
            f"{enable(item.t_start, item.t_end, fps)}"
        )
    return filters
