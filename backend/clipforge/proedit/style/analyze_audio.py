"""The audio features of a style reference (SPEC-v3 4.3 audio).

YAMNet (pipeline/yamnet, the model of the signals step) scores the
reference's audio, decoded to 16 kHz mono (ffmpeg.extract_audio_wav), in
0.96 s frames every 0.48 s (pipeline/audio_analysis, which also gives the
RMS envelope). A frame is speech / music when its "Speech" / "Music"
score is at least ACTIVE_SCORE (the signals step's); the shares are of all
frames, and the reference has music when at least MUSIC_PRESENT of its
frames do.

With music, the beat grid of the audio (beats.music_grid: tempo, beats,
drops) gives the BPM and the drop positions (seconds). A drop has a
silence before it when, in the SILENCE_LOOKBACK_S before it, the audio
stays at least SILENCE_BELOW_DB under the drop's level (the first beat
after it) for SILENCE_MIN_S or more.

SFX are the onsets of the audio (librosa.onset.onset_detect on the beat
grid's samples) that are neither in speech (a speech frame covers them)
nor on the music: within ON_BEAT_S of a beat or half-beat (where the
music's own hats and snares hit) of the regular grid at the BPM through the
tracked beats (which themselves snap onto loud SFX). The loudness curve is the
RMS level (dBFS) of every CURVE_STEP_S window (critic/audio_summary).
"""

import tempfile
from pathlib import Path

import librosa
import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field

from clipforge.ffmpeg import FFmpegError, extract_audio_wav, probe_media
from clipforge.models import UnitInterval
from clipforge.pipeline import audio_analysis, yamnet
from clipforge.pipeline.loudness import CENTER_S, HOP_S, Envelope
from clipforge.pipeline.signals import ACTIVE_SCORE
from clipforge.pipeline.step import StepError
from clipforge.pipeline.yamnet import Yamnet
from clipforge.proedit.beats import HOP, SAMPLE_RATE, grid_of_samples, read_samples
from clipforge.proedit.critic.audio_summary import CURVE_STEP_S, loudness_curve

SPEECH = "Speech"
MUSIC = "Music"
MUSIC_PRESENT = 0.25
ON_BEAT_S = 0.07
SILENCE_LOOKBACK_S = 1.0
SILENCE_BELOW_DB = 30.0
SILENCE_MIN_S = 0.1
DECIMALS = 4

Floats = npt.NDArray[np.float64]


class AudioFeatures(BaseModel):
    """The audio of a reference (module doc): speech and music shares,
    whether it has music, its tempo, the loudness curve (dBFS per
    loudness_step_s), drops (seconds), how many drops have a silence before
    them, the SFX onsets (seconds) and how many come per minute."""

    speech_share: UnitInterval
    music_share: UnitInterval
    has_music: bool
    bpm: float | None = None
    loudness_step_s: float = Field(default=CURVE_STEP_S, gt=0)
    loudness_curve: list[float]
    drops: list[float]
    silence_before_drop: int = Field(ge=0)
    sfx_onsets: list[float]
    sfx_per_minute: float = Field(ge=0)


def analyze_audio(path: Path, model: Yamnet) -> AudioFeatures | None:
    """Return the audio features of the video at path (module doc), or None
    if it has no audio stream. Raises StepError if it cannot be decoded."""
    try:
        info = probe_media(path)
        if not info.audio_codec:
            return None
        with tempfile.TemporaryDirectory(prefix="clipforge-style-") as tmp:
            wav = extract_audio_wav(path, Path(tmp) / "audio.wav")
            analysis = audio_analysis.analyze_audio(
                wav,
                0.0,
                info.duration,
                model,
                [model.class_index(SPEECH), model.class_index(MUSIC)],
            )
    except FFmpegError as exc:
        raise StepError(f"cannot read the audio of {path}: {exc}") from exc
    samples = read_samples(path)
    duration = len(samples) / SAMPLE_RATE
    speech = analysis.scores[:, 0] >= ACTIVE_SCORE
    music = analysis.scores[:, 1] >= ACTIVE_SCORE
    music_share = _share(music)
    grid = (
        grid_of_samples(samples, SAMPLE_RATE) if music_share >= MUSIC_PRESENT else None
    )
    beats = grid.beats if grid else []
    onsets = librosa.onset.onset_detect(
        y=samples, sr=SAMPLE_RATE, hop_length=HOP, units="time"
    )
    sfx = [
        round(float(t), DECIMALS)
        for t in onsets
        if not _in_frames(float(t), speech)
        and not on_music(float(t), beats, grid.bpm if grid else None)
    ]
    envelope = analysis.envelope
    drops = grid.drops if grid else []
    beat_s = 60 / grid.bpm if grid and grid.bpm else None
    centers = np.asarray(
        envelope.start + CENTER_S + np.arange(len(envelope.levels)) * HOP_S,
        dtype=np.float64,
    )
    return AudioFeatures(
        speech_share=_share(speech),
        music_share=music_share,
        has_music=grid is not None,
        bpm=grid.bpm if grid else None,
        loudness_curve=[
            round(level, 2)
            for level in loudness_curve(envelope.levels, centers, duration)
        ],
        drops=drops,
        silence_before_drop=sum(
            silence_before(envelope, drop, beat_s) for drop in drops if beat_s
        ),
        sfx_onsets=sfx,
        sfx_per_minute=round(len(sfx) / (duration / 60), DECIMALS) if duration else 0.0,
    )


def on_music(time: float, beats: list[float], bpm: float | None) -> bool:
    """Return whether time is within ON_BEAT_S of a beat or a half-beat of
    the regular grid at bpm through the beats (its phase is the circular
    mean of the beats; tracked beats themselves snap to loud SFX)."""
    if not beats or not bpm:
        return False
    period = 60 / bpm
    angles = 2 * np.pi * np.asarray(beats, dtype=np.float64) / period
    phase = float(np.angle(np.mean(np.exp(1j * angles)))) * period / (2 * np.pi)
    offset = (time - phase) % (period / 2)
    return min(offset, period / 2 - offset) <= ON_BEAT_S + 1e-9


def silence_before(envelope: Envelope, drop: float, beat_s: float) -> bool:
    """Return whether the audio goes quiet before the drop (module doc)."""
    level = envelope.level(drop, drop + beat_s)
    if level is None:
        return False
    before = envelope.between(max(0.0, drop - SILENCE_LOOKBACK_S), drop - HOP_S)
    quiet = before <= level - SILENCE_BELOW_DB
    longest = run = 0
    for frame in quiet:
        run = run + 1 if frame else 0
        longest = max(longest, run)
    return longest * HOP_S >= SILENCE_MIN_S - 1e-9


def _in_frames(time: float, active: npt.NDArray[np.bool_]) -> bool:
    """Return whether an active YAMNet frame covers time (frame i covers
    [i * hop, i * hop + window) seconds)."""
    hop = yamnet.HOP_SAMPLES / yamnet.SAMPLE_RATE
    window = yamnet.WINDOW_SAMPLES / yamnet.SAMPLE_RATE
    first = max(0, int(np.floor((time - window) / hop)))
    last = min(len(active) - 1, int(np.floor(time / hop)))
    return any(
        active[i] and i * hop <= time < i * hop + window for i in range(first, last + 1)
    )


def _share(frames: npt.NDArray[np.bool_]) -> float:
    """Return the share of the frames that are active, 0 without frames."""
    return round(float(np.mean(frames)), DECIMALS) if len(frames) else 0.0
