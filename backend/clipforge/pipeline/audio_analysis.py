"""One pass over the audio of a job's timeframe (SPEC 6.3): YAMNet + RMS.

audio.wav, which ingest writes, is 16 kHz mono 16-bit PCM. Its timeframe is
read in chunks of FRAMES_PER_CHUNK YAMNet frames, so that long audio never
has to fit in memory at once. Each chunk is scored by YAMNet (pipeline/yamnet)
and measured by librosa (pipeline/loudness). A chunk also holds the samples
that its last frame reads past the start of the next chunk, and starts at a
whole number of YAMNet hops (which is also a whole number of RMS hops), so
every frame and every RMS frame reads the same samples as in one pass over
the whole timeframe.
"""

import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from clipforge.pipeline import loudness, yamnet
from clipforge.pipeline.loudness import Envelope
from clipforge.pipeline.step import StepError
from clipforge.pipeline.yamnet import Yamnet

FRAMES_PER_CHUNK = 125  # 60 s of audio per model run
# 16-bit samples are divided by this to get -1..1.
FULL_SCALE = np.float32(32768)


@dataclass(frozen=True)
class AudioAnalysis:
    """The YAMNet scores and RMS envelope of the audio in [start, end] s.

    scores has one row per YAMNet frame, the first one starting at start,
    and one column per class analyzed.
    """

    start: float
    end: float
    scores: npt.NDArray[np.float32]
    envelope: Envelope


def analyze_audio(
    path: Path,
    start: float,
    end: float,
    model: Yamnet,
    columns: list[int],
    *,
    frames_per_chunk: int = FRAMES_PER_CHUNK,
    on_progress: Callable[[float], None] | None = None,
) -> AudioAnalysis:
    """Score the classes columns in [start, end] s of the WAV file at path.

    Also measures the RMS envelope there. The audio is read in chunks of
    frames_per_chunk frames; on_progress gets the fraction of the audio done
    after each chunk. The analysis ends where the file does if that is
    before end. Raises StepError if the file is not 16 kHz mono 16-bit PCM.
    """
    hop = frames_per_chunk * yamnet.HOP_SAMPLES
    chunk_size = hop + yamnet.WINDOW_SAMPLES - yamnet.HOP_SAMPLES
    scores: list[npt.NDArray[np.float32]] = []
    levels: list[loudness.Levels] = []
    with open_wav(path) as wav:
        first = min(round(start * yamnet.SAMPLE_RATE), wav.getnframes())
        last = min(round(end * yamnet.SAMPLE_RATE), wav.getnframes())
        offset = first
        while offset < last:
            wav.setpos(offset)
            raw = wav.readframes(min(chunk_size, last - offset))
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / FULL_SCALE
            chunk_scores = model.scores(samples)[:, columns]
            chunk_levels = loudness.rms_db(samples)
            if offset + chunk_size < last:
                # Not the last chunk, which has frames_per_chunk frames: keep
                # the RMS frames before the next chunk too.
                chunk_levels = chunk_levels[: hop // loudness.HOP_SAMPLES]
                offset += hop
            else:
                offset = last
            scores.append(chunk_scores)
            levels.append(chunk_levels)
            if on_progress is not None:
                on_progress((offset - first) / (last - first))
    time_start = first / yamnet.SAMPLE_RATE
    return AudioAnalysis(
        start=time_start,
        end=last / yamnet.SAMPLE_RATE,
        scores=(
            np.concatenate(scores)
            if scores
            else np.zeros((0, len(columns)), dtype=np.float32)
        ),
        envelope=Envelope(
            time_start,
            np.concatenate(levels) if levels else np.zeros(0, dtype=np.float32),
        ),
    )


def open_wav(path: Path) -> wave.Wave_read:
    """Open the WAV file at path, which must be 16 kHz mono 16-bit PCM.

    Raises StepError if it cannot be read or has another format.
    """
    try:
        wav = wave.open(str(path), "rb")
    except (wave.Error, EOFError, OSError) as exc:
        raise StepError(f"cannot read {path}: {exc}") from exc
    found = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
    if found != (1, 2, yamnet.SAMPLE_RATE):
        wav.close()
        raise StepError(
            f"{path} is not 16 kHz mono 16-bit PCM: {found[0]} channel(s), "
            f"{found[1] * 8}-bit, {found[2]} Hz; run the ingest step again"
        )
    return wav
