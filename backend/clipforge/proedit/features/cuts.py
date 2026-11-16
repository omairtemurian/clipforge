"""Cut rhythm of a video (SPEC-v3 4.3): hard cuts, shot lengths and the
cuts-per-second curve, plus the beat share of any event times.

Each sampled frame is described by the luma histograms (BINS bins) of the
cells of a GRID x GRID grid; the distance of two frames is the mean over
the cells of half the L1 distance of their histograms (0 same, 1 nothing in
common). Histograms barely change when the camera zooms, pans or shakes, or
when a grade drops the color (B&W keeps the luma), so those are not cuts.
Flash frames (features/flashes) are skipped. Frame k starts a new shot when
it and the CONFIRM_FRAMES frames after it are each at least CUT_DISTANCE
from each of the CONFIRM_FRAMES + 1 frames before it: the new shot stays,
and one odd frame (a flash, a glitch) makes no cut, nor does the return
from it. Shots shorter than CONFIRM_FRAMES + 1 frames, dissolves and fades
are not detected.
"""

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field

from clipforge.proedit.features.color import Frame, luma_plane

GRID = 2
BINS = 16
CUT_DISTANCE = 0.3
CONFIRM_FRAMES = 2
DECIMALS = 4

Descriptor = npt.NDArray[np.float32]


class CutStats(BaseModel):
    """The cuts of a video (seconds), its shot lengths (seconds, from the
    start to the end), their mean, the number of cuts in each second and
    the cuts per minute."""

    cuts: list[float]
    shot_lengths: list[float]
    mean_shot_s: float = Field(ge=0)
    cuts_per_second: list[int]
    per_minute: float = Field(ge=0)


def frame_descriptor(rgb: Frame) -> Descriptor:
    """Return the cell luma histograms of the RGB frame rgb, each summing to 1,
    as one array of shape (GRID * GRID, BINS)."""
    luma = luma_plane(rgb)
    height, width = luma.shape
    cells = []
    for row in range(GRID):
        for column in range(GRID):
            cell = luma[
                row * height // GRID : (row + 1) * height // GRID,
                column * width // GRID : (column + 1) * width // GRID,
            ]
            counts, _ = np.histogram(cell, bins=BINS, range=(0, 256))
            cells.append(counts / max(cell.size, 1))
    return np.asarray(cells, dtype=np.float32)


def distance(a: Descriptor, b: Descriptor) -> float:
    """Return the distance (0..1) of two frame descriptors (module doc)."""
    return float(np.abs(a - b).sum(axis=1).mean() / 2)


def detect_cuts(
    descriptors: Sequence[Descriptor], flashes: Sequence[bool] = ()
) -> list[int]:
    """Return the indexes of the frames that start a new shot (module doc);
    flashes[k] tells whether frame k is a flash (none if empty)."""
    kept = [k for k in range(len(descriptors)) if not (flashes and flashes[k])]
    cuts = []
    for position in range(1, len(kept)):
        before = kept[max(0, position - 1 - CONFIRM_FRAMES) : position]
        after = kept[position : position + 1 + CONFIRM_FRAMES]
        if all(
            distance(descriptors[a], descriptors[b]) >= CUT_DISTANCE
            for a in before
            for b in after
        ):
            cuts.append(kept[position])
    return cuts


def cut_stats(cut_frames: Sequence[int], frame_count: int, fps: float) -> CutStats:
    """Return the cut rhythm of a video of frame_count frames at fps whose
    shots start at the frames cut_frames (besides frame 0)."""
    duration = frame_count / fps
    cuts = [round(k / fps, DECIMALS) for k in cut_frames]
    edges = [0.0, *cuts, round(duration, DECIMALS)]
    shots = [round(b - a, DECIMALS) for a, b in zip(edges, edges[1:], strict=False)]
    seconds = int(np.ceil(round(duration, 6)))
    per_second = [0] * seconds
    for cut in cuts:
        per_second[min(int(cut), seconds - 1)] += 1
    return CutStats(
        cuts=cuts,
        shot_lengths=shots,
        mean_shot_s=round(float(np.mean(shots)), DECIMALS) if shots else 0.0,
        cuts_per_second=per_second,
        per_minute=round(len(cuts) / (duration / 60), DECIMALS) if duration else 0.0,
    )


def on_beat_share(
    times: Sequence[float], beats: Sequence[float], tolerance: float
) -> float:
    """Return the share (0..1) of times within tolerance seconds of a beat;
    0 without times."""
    if not times:
        return 0.0
    grid = np.sort(np.asarray(beats, dtype=np.float64))
    hits = 0
    for time in times:
        if len(grid):
            index = int(np.searchsorted(grid, time))
            near = grid[max(index - 1, 0) : index + 1]
            hits += bool(np.min(np.abs(near - time)) <= tolerance + 1e-9)
    return round(hits / len(times), DECIMALS)


def mean_interval(times: Sequence[float]) -> float | None:
    """Return the mean gap (seconds) between consecutive distinct times, or
    None with fewer than two."""
    ordered = sorted(set(times))
    if len(ordered) < 2:
        return None
    return round(float(np.mean(np.diff(ordered))), DECIMALS)
