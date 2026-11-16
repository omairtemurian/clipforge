"""The audio summary the Pro Edit critic reads (SPEC-v3 3.7).

From the proxy render's mix (rendered-clip seconds):

- integrated loudness (LUFS) and true peak (dBTP): loudnorm's measurement,
  as the mastering step measures it (None for silence);
- the sample peak (dBFS) and the clipped samples: samples of any channel,
  at 48 kHz, at or above CLIP_LEVEL of full scale;
- the loudness curve: the RMS level (dBFS) of every CURVE_STEP_S window,
  from pipeline/loudness's 25 ms frames of the 16 kHz mono mix;
- speech, music and SFX levels: the RMS level (power mean of those frames)
  where words are spoken and no SFX plays, where the music bed plays alone
  (no words, no SFX) and where SFX items play; a frame that overlaps an
  excluded span at all is left out. The mix has no stems, so the
  music level is the bed where nobody speaks; speech_over_music_db is
  speech minus music. A level is None when no frame is in its spans.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field

from clipforge.ffmpeg import WAV_SAMPLE_RATE, FFmpegError, run_ffmpeg
from clipforge.models import EdlItem
from clipforge.pipeline.loudness import CENTER_S, FLOOR_DB, HOP_S, rms_db
from clipforge.pipeline.loudnorm import measure_filter, measure_loudness
from clipforge.pipeline.step import StepError
from clipforge.proedit.beats import read_samples
from clipforge.proedit.signal_models import WordSignal

CURVE_STEP_S = 0.5
CLIP_LEVEL = 0.999
PEAK_RATE = 48_000
TARGET_LUFS = -14.0
DECIMALS = 1

Span = tuple[float, float]


class AudioSummary(BaseModel):
    """What the critic hears in the mix (module docstring)."""

    integrated_lufs: float | None
    true_peak_dbtp: float | None
    peak_dbfs: float
    clipped_samples: int = Field(ge=0)
    curve_step_s: float = CURVE_STEP_S
    loudness_curve: list[float]
    speech_db: float | None
    music_db: float | None
    sfx_db: float | None
    speech_over_music_db: float | None


def summarize_audio(
    video: Path,
    items: Sequence[EdlItem],
    words: Sequence[WordSignal],
    duration: float,
) -> AudioSummary:
    """Return the summary of video's mix for a plan's items and the clip's
    words. Raises StepError if ffmpeg cannot decode or measure it."""
    levels = rms_db(read_samples(video, WAV_SAMPLE_RATE))
    centers = CENTER_S + HOP_S * np.arange(len(levels), dtype=np.float64)
    speech = [(w.start, w.end) for w in words]
    sfx = [(i.t_start, i.t_end) for i in items if i.kind == "sfx"]
    music = [(i.t_start, i.t_end) for i in items if i.kind == "music_bed"]
    in_speech, in_sfx = _mask(centers, speech), _mask(centers, sfx)
    near_speech = _mask(centers, speech, CENTER_S)
    near_sfx = _mask(centers, sfx, CENTER_S)
    speech_db = _level(levels, in_speech & ~near_sfx)
    music_db = _level(levels, _mask(centers, music) & ~near_speech & ~near_sfx)
    peak, clipped = sample_peak(video)
    loudness = _loudness(video)
    return AudioSummary(
        integrated_lufs=None if loudness is None else loudness[0],
        true_peak_dbtp=None if loudness is None else loudness[1],
        peak_dbfs=peak,
        clipped_samples=clipped,
        loudness_curve=loudness_curve(levels, centers, duration),
        speech_db=speech_db,
        music_db=music_db,
        sfx_db=_level(levels, in_sfx),
        speech_over_music_db=(
            None
            if speech_db is None or music_db is None
            else round(speech_db - music_db, DECIMALS)
        ),
    )


def loudness_curve(
    levels: npt.NDArray[np.float32], centers: npt.NDArray[np.float64], duration: float
) -> list[float]:
    """Return the level (dBFS) of each CURVE_STEP_S window of the clip, the
    floor for a window without frames."""
    windows = max(1, int(np.ceil(duration / CURVE_STEP_S - 1e-9)))
    curve = []
    for n in range(windows):
        start = n * CURVE_STEP_S
        inside = (centers >= start) & (centers < start + CURVE_STEP_S)
        level = _level(levels, inside)
        curve.append(FLOOR_DB if level is None else level)
    return curve


def sample_peak(video: Path) -> tuple[float, int]:
    """Return the sample peak (dBFS) of video's audio and how many samples
    (any channel) reach CLIP_LEVEL."""
    try:
        result = run_ffmpeg(
            [
                "-i", video, "-map", "0:a:0", "-vn", "-ar", str(PEAK_RATE),
                "-f", "f32le", "pipe:1",
            ]
        )  # fmt: skip
    except FFmpegError as exc:
        raise StepError(f"cannot read the audio of {video}: {exc}") from exc
    data = result.stdout[: len(result.stdout) // 4 * 4]
    samples = np.abs(np.frombuffer(data, dtype="<f4"))
    if not len(samples) or float(samples.max()) <= 0:
        return FLOOR_DB, 0
    peak = max(20 * float(np.log10(samples.max())), FLOOR_DB)
    return round(peak, DECIMALS), int(np.count_nonzero(samples >= CLIP_LEVEL))


def _loudness(video: Path) -> tuple[float, float] | None:
    graph = f"[0:a:0]{measure_filter(TARGET_LUFS)}[m]"
    try:
        measured = measure_loudness(["-i", video], graph, "[m]")
    except FFmpegError as exc:
        raise StepError(f"cannot measure the loudness of {video}: {exc}") from exc
    if measured is None:
        return None
    return round(measured.integrated, DECIMALS), round(measured.true_peak, DECIMALS)


def _mask(
    centers: npt.NDArray[np.float64], spans: Sequence[Span], pad: float = 0.0
) -> npt.NDArray[np.bool_]:
    """Whether each frame's center is in one of spans widened by pad on
    both sides (pad CENTER_S: the frame overlaps the span)."""
    inside = np.zeros(len(centers), dtype=bool)
    for start, end in spans:
        inside |= (centers >= start - pad) & (centers <= end + pad)
    return inside


def _level(
    levels: npt.NDArray[np.float32], where: npt.NDArray[np.bool_]
) -> float | None:
    """The power mean (dBFS) of the levels where is true; None if nowhere."""
    chosen = levels[where].astype(np.float64)
    if not len(chosen):
        return None
    return round(float(10 * np.log10(np.mean(10 ** (chosen / 10)))), DECIMALS)
