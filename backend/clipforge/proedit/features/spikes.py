"""Glitches of a video (SPEC-v3 4.3 flashes/glitches): frame-difference
spikes and RGB splits.

A spike is a run of at most MAX_SPIKE_FRAMES odd frames: each differs from
the frame before the run by at least SPIKE_DIFF (mean absolute difference
of the grey frames, 0..1), and the frame after the run is back near the
frame before it (its difference at most RETURN_SHARE of the jump into the
run). A cut does not come back, so it is no spike; flashes (features/
flashes) and RGB-split frames are counted on their own and make no spike.
Of overlapping candidates the earliest, then shortest, wins.

RGB splits are the runs of frames that features/glitches.channel_offset
calls split.
"""

from collections import deque
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field

from clipforge.proedit.features.color import Span, runs

SPIKE_DIFF = 0.08
RETURN_SHARE = 0.35
MAX_SPIKE_FRAMES = 2
DECIMALS = 4

Grey = npt.NDArray[np.uint8]


class GlitchStats(BaseModel):
    """The RGB-split spans and frame-difference spikes of a video, and how
    many of both come per minute."""

    splits: list[Span]
    spikes: list[Span]
    per_minute: float = Field(ge=0)


class SpikeFinder:
    """Finds the candidate spikes of a video's grey frames as they come in
    (add), keeping only the last few frames."""

    def __init__(self) -> None:
        self._greys: deque[npt.NDArray[np.float32]] = deque(maxlen=MAX_SPIKE_FRAMES + 2)
        self._index = -1
        self.candidates: list[tuple[int, int]] = []

    def add(self, grey: Grey) -> None:
        """Take the next grey frame and note each run of odd frames that it
        ends, as (first, end) frame indexes (end exclusive)."""
        self._index += 1
        self._greys.append(np.asarray(grey, dtype=np.float32) / np.float32(255))
        frames = list(self._greys)
        for length in range(1, MAX_SPIKE_FRAMES + 1):
            if len(frames) < length + 2:
                break
            before, odd, after = (
                frames[-2 - length],
                frames[-1 - length : -1],
                frames[-1],
            )
            jump = _difference(before, odd[0])
            if (
                jump >= SPIKE_DIFF
                and all(_difference(before, frame) >= SPIKE_DIFF for frame in odd)
                and _difference(before, after) <= RETURN_SHARE * jump
            ):
                self.candidates.append((self._index - length, self._index))


def glitch_stats(
    candidates: Sequence[tuple[int, int]],
    split: Sequence[bool],
    excluded: Sequence[bool],
    fps: float,
) -> GlitchStats:
    """Return the glitches of a video whose frame k (k / fps seconds) is an
    RGB split when split[k], from its spike candidates (SpikeFinder);
    candidates touching a split frame or a frame excluded[k] (a flash, a
    cut) are dropped."""
    spikes: list[Span] = []
    taken_until = 0
    for first, end in sorted(candidates):
        if first < taken_until:
            continue
        if any(split[k] or excluded[k] for k in range(first, min(end, len(split)))):
            continue
        spikes.append(
            Span(start=round(first / fps, DECIMALS), end=round(end / fps, DECIMALS))
        )
        taken_until = end
    splits = [Span(start=a, end=b) for a, b in runs(split, fps)]
    minutes = len(split) / fps / 60
    count = len(splits) + len(spikes)
    return GlitchStats(
        splits=splits,
        spikes=spikes,
        per_minute=round(count / minutes, DECIMALS) if minutes else 0.0,
    )


def _difference(a: npt.NDArray[np.float32], b: npt.NDArray[np.float32]) -> float:
    """Return the mean absolute difference (0..1) of two grey frames."""
    return float(np.abs(a - b).mean())
