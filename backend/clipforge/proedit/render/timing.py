"""When a Pro Edit item is drawn: the frames of its window on the rendered
clip's frame grid, as a filter's timeline option (enable) or as frame
numbers (frame_range)."""

import math

DECIMALS = 6


def frame_window(t_start: float, t_end: float, fps: int) -> str:
    """Return the timeline expression that is true on the frames of the
    rendered clip (time t) from t_start up to, not including, t_end seconds:
    for times on the frame grid (snap.py), the frames n with
    t_start <= n / fps < t_end; other times go to the nearest frame.

    Both bounds move half a frame earlier, so float noise in a frame's
    time cannot carry it across a bound.
    """
    half = 0.5 / fps
    low, high = round(t_start - half, DECIMALS), round(t_end - half, DECIMALS)
    return f"gte(t,{low:.{DECIMALS}f})*lt(t,{high:.{DECIMALS}f})"


def enable(t_start: float, t_end: float, fps: int) -> str:
    """Return the enable option (quoted, so its commas stay inside it) that
    draws a filter only on the frames of frame_window."""
    return f"enable='{frame_window(t_start, t_end, fps)}'"


def frame_range(t_start: float, t_end: float, fps: int) -> tuple[int, int]:
    """Return the first frame of frame_window(t_start, t_end, fps) and the
    frame after its last (equal when it holds no frame), for filters that
    count frames instead of reading t."""
    first = math.ceil(round(t_start * fps - 0.5, DECIMALS))
    end = math.ceil(round(t_end * fps - 0.5, DECIMALS))
    return first, max(first, end)
