"""Effects drawn on a window of a Pro Edit render only (fx_glitch,
fx_transition): the stream is split; one copy makes the window's frames
from the other's (a branch, which may change the pixel format), is turned
back to fx_basic.YUV_FORMAT, delayed to the window by `tpad` start frames
(generated frames, so the main copy never waits on it; motion_time) and
drawn over the main copy on the window's frames (`overlay` enable,
eof_action=pass). Frames outside the window pass through untouched, bit
for bit."""

from collections.abc import Callable

from clipforge.proedit.render.fx_basic import YUV_FORMAT
from clipforge.proedit.render.timing import enable

Branch = Callable[[str], str]


def window_frames(source: str, first: int, end: int) -> str:
    """Return source's frames first..end-1 (from 0) timed from 0, as the
    start of a chain."""
    return f"{source}trim=start_frame={first}:end_frame={end},setpts=PTS-STARTPTS"


def over_window(name: str, first: int, end: int, fps: int, branch: Branch) -> str:
    """Return the filter that draws the frames that branch makes (from the
    label of a copy of the stream, ending unlabeled) on frames first..end-1
    of the stream at fps (module doc); name keeps its labels apart."""
    main, source, window = (f"[{name}{part}]" for part in ("main", "src", "win"))
    return (
        f"split{main}{source};{branch(source)},{YUV_FORMAT},tpad=start={first}"
        f"{window};{main}{window}overlay=eof_action=pass:repeatlast=0:"
        f"{enable(first / fps, end / fps, fps)}"
    )
