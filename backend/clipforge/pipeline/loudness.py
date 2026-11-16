"""Loudness of the job's audio (SPEC 6.3): an RMS envelope in dBFS.

librosa computes the RMS of 25 ms frames every 10 ms (the STFT framing of
YAMNet) of the 16 kHz audio that ingest writes, in dB relative to full scale
(amplitude 1): a full-scale sine is at -3 dB, digital silence at the floor,
-100 dB.
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from clipforge.ffmpeg import WAV_SAMPLE_RATE as SAMPLE_RATE

FRAME_SAMPLES = 400
HOP_SAMPLES = 160
HOP_S = HOP_SAMPLES / SAMPLE_RATE
# Frame k covers samples [160 k, 160 k + 400); its center is 12.5 ms in.
CENTER_S = FRAME_SAMPLES / 2 / SAMPLE_RATE
FLOOR_DB = -100.0
# A frame centered this close (seconds) outside a span counts as in it, so
# float error in times such as 10.0125 never drops a frame.
EPSILON_S = 1e-6

Levels = npt.NDArray[np.float32]


def rms_db(samples: npt.NDArray[np.float32]) -> Levels:
    """Return the RMS level (dBFS) of each frame of samples (16 kHz, -1..1).

    Frame k covers samples [160 k, 160 k + 400); a last frame that would
    run past the end of samples is left out, so there are none for fewer
    than 400 samples.
    """
    if len(samples) < FRAME_SAMPLES:
        return np.zeros(0, dtype=np.float32)
    import librosa

    rms = librosa.feature.rms(
        y=samples, frame_length=FRAME_SAMPLES, hop_length=HOP_SAMPLES, center=False
    )[0]
    levels = librosa.amplitude_to_db(
        rms, ref=1.0, amin=10 ** (FLOOR_DB / 20), top_db=None
    )
    return np.asarray(levels, dtype=np.float32)


@dataclass(frozen=True)
class Envelope:
    """The RMS levels of audio that starts at source time start (seconds).

    levels[k] is the level (dBFS) of the frame centered at
    start + 0.0125 + 0.01 k.
    """

    start: float
    levels: Levels

    def center(self, index: int) -> float:
        """Return the source time (seconds) of the center of frame index."""
        return self.start + CENTER_S + index * HOP_S

    def between(self, start: float, end: float) -> Levels:
        """Return the levels of the frames centered in [start, end]."""
        first = math.ceil((start - EPSILON_S - self.start - CENTER_S) / HOP_S)
        last = math.floor((end + EPSILON_S - self.start - CENTER_S) / HOP_S)
        return self.levels[max(first, 0) : max(last + 1, 0)]

    def level(self, start: float, end: float) -> float | None:
        """Return the level (dBFS) of the audio in [start, end].

        It is the mean power of the frames centered there, or None if there
        are none.
        """
        levels = self.between(start, end).astype(np.float64)
        if not len(levels):
            return None
        return float(10 * np.log10(np.mean(10 ** (levels / 10))))

    def baseline(self, time: float, window: float) -> float | None:
        """Return the rolling median level (dBFS) at time.

        It is the median level of the frames centered in the window seconds
        around time (fewer near the ends of the audio), or None if there are
        none.
        """
        levels = self.between(time - window / 2, time + window / 2)
        return float(np.median(levels)) if len(levels) else None
