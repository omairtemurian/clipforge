"""The beat grid of a music asset (SPEC-v3 3.2): beats, downbeats and drops.

ffmpeg decodes the music to mono SAMPLE_RATE float samples. librosa finds
the beats: `onset.onset_strength` (hop HOP samples) feeds
`beat.beat_track(..., trim=False)` (trim would drop the beats of quiet
passages). The tracker's times sit on its 11.6 ms hop and lag the
transients by ~20 ms, so each beat moves to the steepest rise of a short
window energy (ATTACK_FRAME samples every ATTACK_HOP) within
REFINE_WINDOW_S of it when that rise is a clear attack (ATTACK_RISE); beats
without one (extrapolated through a break) move by the median shift of the
others, and those before the first attack or after the last are dropped
(the tracker running on into silence). The tempo is 60 over the median
beat interval.

Downbeats assume 4/4: of the four phases, the one whose beats are loudest
on average starts the bars. A beat's level is the mean power of the audio
from it to the next beat. A drop is a beat whose own level and the median
level of the bar from it (DROP_AFTER beats) are within DROP_LOUD_DB of the
track's loud level (its DROP_LOUD_PERCENTILE percentile) and at least
DROP_RISE_DB above the median level of the two bars before it (DROP_BEFORE
beats; medians, so a riser or one stray loud beat does not hide the rise);
of drops closer than DROP_SPACING beats the larger rise wins.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field

from clipforge.ffmpeg import FFmpegError, run_ffmpeg
from clipforge.pipeline.step import StepError

SAMPLE_RATE = 22_050
HOP = 256
ATTACK_FRAME = 256
ATTACK_HOP = 32
REFINE_WINDOW_S = 0.07
# Natural-log energy rise between two attack frames (x4 = +6 dB).
ATTACK_RISE = float(np.log(4.0))
# Attack frames quieter than this (dB below the track's loudest) count as silence.
SILENCE_DB = 60.0
BEATS_PER_BAR = 4
DROP_BEFORE = 8
DROP_AFTER = 4
DROP_RISE_DB = 6.0
DROP_LOUD_PERCENTILE = 75
DROP_LOUD_DB = 3.0
DROP_SPACING = 8
MIN_BEATS = 4
DECIMALS = 4

Samples = npt.NDArray[np.float32]


class MusicGrid(BaseModel):
    """The beat grid of a piece of music; times in seconds of the music.
    bpm is None when fewer than MIN_BEATS beats were found."""

    duration: float = Field(ge=0)
    bpm: float | None = Field(default=None, gt=0)
    beats: list[float] = []
    downbeats: list[float] = []
    drops: list[float] = []


def music_grid(path: Path) -> MusicGrid:
    """Return the beat grid of the first audio stream of path.

    Raises StepError if ffmpeg cannot decode it.
    """
    return grid_of_samples(read_samples(path), SAMPLE_RATE)


def read_samples(path: Path, sample_rate: int = SAMPLE_RATE) -> Samples:
    """Return the mono float samples (-1..1) of path's first audio stream at
    sample_rate. Raises StepError if ffmpeg cannot decode it."""
    try:
        result = run_ffmpeg(
            [
                "-i", path, "-map", "0:a:0", "-vn", "-ac", "1",
                "-ar", str(sample_rate), "-f", "f32le", "pipe:1",
            ]
        )  # fmt: skip
    except FFmpegError as exc:
        raise StepError(f"cannot read the music of {path}: {exc}") from exc
    data = result.stdout[: len(result.stdout) // 4 * 4]
    return np.frombuffer(data, dtype="<f4").astype(np.float32)


def grid_of_samples(samples: Samples, sample_rate: int) -> MusicGrid:
    """Return the beat grid of mono samples at sample_rate (module doc)."""
    import librosa

    duration = round(len(samples) / sample_rate, DECIMALS)
    if len(samples) < sample_rate:
        return MusicGrid(duration=duration)
    envelope = librosa.onset.onset_strength(y=samples, sr=sample_rate, hop_length=HOP)
    _, frames = librosa.beat.beat_track(
        onset_envelope=envelope, sr=sample_rate, hop_length=HOP, trim=False
    )
    raw = librosa.frames_to_time(frames, sr=sample_rate, hop_length=HOP)
    beats = _refine(np.asarray(raw, dtype=np.float64), samples, sample_rate)
    beats = [b for b in beats if 0 <= b < duration]
    if len(beats) < MIN_BEATS:
        return MusicGrid(duration=duration, beats=[round(b, DECIMALS) for b in beats])
    levels = beat_levels(beats, samples, sample_rate)
    return MusicGrid(
        duration=duration,
        bpm=round(60.0 / float(np.median(np.diff(beats))), 2),
        beats=[round(b, DECIMALS) for b in beats],
        downbeats=[round(b, DECIMALS) for b in downbeats(beats, levels)],
        drops=[round(b, DECIMALS) for b in drops(beats, levels)],
    )


def _refine(raw: npt.NDArray[np.float64], samples: Samples, rate: int) -> list[float]:
    """Return the beats raw moved onto their attacks (module doc)."""
    import librosa

    # Silence in front, so an attack at sample 0 is a rise too.
    padded = np.concatenate([np.zeros(ATTACK_FRAME, np.float32), samples])
    rms = librosa.feature.rms(
        y=padded, frame_length=ATTACK_FRAME, hop_length=ATTACK_HOP, center=False
    )[0]
    power = rms.astype(np.float64) ** 2
    floor = max(float(power.max()), 1e-12) * 10 ** (-SILENCE_DB / 10)
    rise = np.diff(np.log(np.maximum(power, floor)))
    # Rise k is frame k+1 against frame k; frame k+1 ends at padded sample
    # (k+1) * hop + frame, sample (k+1) * hop of samples, and the attack
    # entered it within its last hop.
    rise_times = ((np.arange(len(rise)) + 1) * ATTACK_HOP - ATTACK_HOP / 2) / rate
    refined: list[float | None] = []
    for beat in raw:
        lo, hi = np.searchsorted(
            rise_times, [beat - REFINE_WINDOW_S, beat + REFINE_WINDOW_S]
        )
        window = rise[lo:hi]
        if len(window) and float(window.max()) >= ATTACK_RISE:
            refined.append(float(rise_times[lo + int(np.argmax(window))]))
        else:
            refined.append(None)
    attacked = [i for i, r in enumerate(refined) if r is not None]
    if not attacked:
        return sorted({float(b) for b in raw})
    shift = float(
        np.median([r - b for r, b in zip(refined, raw, strict=True) if r is not None])
    )
    # Beats before the first attack or after the last one are the tracker
    # running on into silence: dropped.
    times = [
        r if r is not None else float(b) + shift
        for r, b in zip(refined, raw, strict=True)
    ][attacked[0] : attacked[-1] + 1]
    return sorted(set(times))


def beat_levels(beats: Sequence[float], samples: Samples, rate: int) -> list[float]:
    """Return the level (dBFS, mean power) of each beat interval: from a beat
    to the next one (the last to the end of the samples)."""
    edges = [int(round(b * rate)) for b in beats] + [len(samples)]
    levels = []
    for start, end in zip(edges, edges[1:], strict=False):
        part = samples[start:end].astype(np.float64)
        power = float(np.mean(part**2)) if len(part) else 0.0
        levels.append(10 * np.log10(max(power, 1e-12)))
    return levels


def downbeats(beats: Sequence[float], levels: Sequence[float]) -> list[float]:
    """Return the beats that start a 4/4 bar: those of the phase (index mod
    BEATS_PER_BAR) whose levels are highest on average (the earliest phase
    on a tie)."""
    means = [
        float(np.mean(levels[phase::BEATS_PER_BAR]))
        if levels[phase::BEATS_PER_BAR]
        else -np.inf
        for phase in range(BEATS_PER_BAR)
    ]
    phase = int(np.argmax(means))
    return list(beats[phase::BEATS_PER_BAR])


def drops(beats: Sequence[float], levels: Sequence[float]) -> list[float]:
    """Return the beats where the music drops (module doc), in order."""
    loud = float(np.percentile(levels, DROP_LOUD_PERCENTILE))
    rises: list[tuple[float, int]] = []
    for index in range(DROP_BEFORE, len(levels) - DROP_AFTER + 1):
        before = float(np.median(levels[index - DROP_BEFORE : index]))
        after = float(np.median(levels[index : index + DROP_AFTER]))
        loud_enough = min(after, levels[index]) >= loud - DROP_LOUD_DB
        if loud_enough and after - before >= DROP_RISE_DB:
            rises.append((after - before, index))
    chosen: list[int] = []
    for _, index in sorted(rises, key=lambda item: (-item[0], item[1])):
        if all(abs(index - other) >= DROP_SPACING for other in chosen):
            chosen.append(index)
    return [beats[index] for index in sorted(chosen)]


def beats_in_clip(
    times: Sequence[float],
    music_start: float,
    clip_duration: float,
    offset: float = 0.0,
) -> list[float]:
    """Return times (music seconds) in seconds of a clip whose music bed
    starts at clip second music_start, offset seconds into the music: those
    that fall in [0, clip_duration)."""
    shifted = (round(t - offset + music_start, DECIMALS) for t in times)
    return [t for t in shifted if 0 <= t < clip_duration]
