"""Silences and energy peaks (SPEC 6.3), from the RMS envelope of a timeframe.

The envelope (pipeline/loudness) has the level of a 25 ms frame every 10 ms.
Each frame stands for the 10 ms around its center, the first one from the
start of the timeframe and the last one to its end, so that the frames tile
the timeframe; a run of consecutive frames spans the time they stand for.

- silence: a run of frames below -40 dBFS that lasts at least 0.35 s.
- energy peak: a frame whose RMS (an amplitude) has a z-score above 2 among
  the frames centered in the 10 s around it (fewer near the ends of the
  timeframe). A z-score has no scale, so the slight swings of steady noise
  or of a quiet stretch can score as high as a shout: a peak frame must
  also have at least twice the mean RMS of those frames (6 dB more) and not
  be silent. Runs of peak frames at most 0.5 s apart are merged and events
  shorter than 0.2 s are dropped, so that a loud stretch is one event, not
  a flicker of short ones.
"""

import numpy as np
import numpy.typing as npt

from clipforge.pipeline.loudness import HOP_S, Envelope
from clipforge.pipeline.signal_merge import ScoredSpan, merge_active_frames

SILENCE_DB = -40.0
SILENCE_MIN_S = 0.35
ENERGY_WINDOW_S = 10.0
ENERGY_Z = 2.0
# A peak frame's RMS is at least this many times the mean RMS around it.
ENERGY_MIN_RATIO = 2.0
ENERGY_MERGE_GAP_S = 0.5
ENERGY_MIN_S = 0.2

Floats = npt.NDArray[np.float64]
Mask = npt.NDArray[np.bool_]


def silences(envelope: Envelope, end: float) -> list[ScoredSpan]:
    """Return the silences in the audio that envelope measures, by start.

    The audio ends at end (seconds). Each silence has score 1.
    """
    return merge_active_frames(
        frame_runs(envelope, envelope.levels < SILENCE_DB, end),
        threshold=0.0,
        max_gap=0.0,
        min_duration=SILENCE_MIN_S,
    )


def energy_peaks(envelope: Envelope, end: float) -> list[ScoredSpan]:
    """Return the energy peaks in the audio that envelope measures, by start.

    The audio ends at end (seconds). Each peak has score 1.
    """
    levels = envelope.levels.astype(np.float64)
    rms = 10 ** (levels / 20)
    mean, z_scores = rolling_z_scores(rms, round(ENERGY_WINDOW_S / 2 / HOP_S))
    peaks = (
        (z_scores > ENERGY_Z)
        & (rms >= ENERGY_MIN_RATIO * mean)
        & (levels >= SILENCE_DB)
    )
    return merge_active_frames(
        frame_runs(envelope, peaks, end),
        threshold=0.0,
        max_gap=ENERGY_MERGE_GAP_S,
        min_duration=ENERGY_MIN_S,
    )


def rolling_z_scores(values: Floats, half: int) -> tuple[Floats, Floats]:
    """Return the rolling mean of values and the z-score of each value in it.

    Both are over the values at most half positions away from it, fewer near
    the ends. A value whose neighbors are all equal has z-score 0. Rolling
    sums make this linear in the number of values.
    """
    count = len(values)
    offset = float(values.mean()) if count else 0.0
    # Sums of the values minus their mean lose less precision.
    shifted = values - offset
    sums = np.concatenate(([0.0], np.cumsum(shifted)))
    squares = np.concatenate(([0.0], np.cumsum(shifted**2)))
    index = np.arange(count)
    low = np.maximum(index - half, 0)
    high = np.minimum(index + half + 1, count)
    size = high - low
    mean = (sums[high] - sums[low]) / size
    variance = np.maximum((squares[high] - squares[low]) / size - mean**2, 0.0)
    std = np.sqrt(variance)
    z_scores = np.divide(shifted - mean, std, out=np.zeros(count), where=std > 0)
    return mean + offset, z_scores


def frame_runs(envelope: Envelope, mask: Mask, end: float) -> list[ScoredSpan]:
    """Return the spans of the runs of consecutive frames that mask selects.

    mask has one entry per frame of envelope, whose audio ends at end. Frame
    k stands for the 10 ms around its center, the first frame from
    envelope.start and the last one to end. Each span has score 1.
    """
    edges = np.diff(mask.astype(np.int8), prepend=0, append=0)
    firsts = np.flatnonzero(edges == 1)
    lasts = np.flatnonzero(edges == -1) - 1
    final = len(mask) - 1
    runs = []
    for first, last in zip(firsts.tolist(), lasts.tolist(), strict=True):
        start = envelope.start if first == 0 else envelope.center(first) - HOP_S / 2
        stop = end if last == final else envelope.center(last) + HOP_S / 2
        runs.append(ScoredSpan(start, stop, 1.0))
    return runs
