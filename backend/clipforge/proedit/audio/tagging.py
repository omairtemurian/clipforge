"""Auto-tagging of an audio asset (SPEC-v3 5.4): what Pro Edit's director and
SFX engine search the library by.

analyze_audio measures one file: its duration, integrated loudness (ffmpeg's
loudnorm, as the mastering step measures it; None under MIN_LOUDNESS_S, which
EBU R128 cannot gate, or for silence), its energy curve (RMS per second, 0 to
1 of the loudest second), its onset sharpness, a category, a mood and, for
music, the tempo (the beat grid of proedit/beats) and the key.

Onset sharpness (0 to 1) is how fast the sound reaches its peak: the largest
rise, in dB per ATTACK_FRAMES frames of FRAME samples, that ends within
ATTACK_TOP_DB of the peak, counted from at most ATTACK_FLOOR_DB below it,
divided by SHARP_RISE_DB. A click or a hit is 1, a whoosh a few tenths.

Category (CATEGORIES): "music" for a music asset; for a sound of at most
MAX_SOUND_S by the shape of its envelope (frames of FRAME samples, the peak's
place in the sound and the energy of its first and last third), its
sharpness and its spectrum: "click" (sharp, shorter than CLICK_S), "chime"
(sharp, tonal, bright), "impact" (sharp, peak early), "riser" (peak late,
last third RISER_GAIN times the first), "whoosh" (soft attack, peak inside)
and "other". Mood is the energy class "calm", "medium" or "intense" from
loudness above the floor, brightness and, for music, tempo; an optional LLM
tag from the file name or metadata (SPEC-v3 5.4) is not made: the heuristics
are what the library searches by.

The key is found by proedit/audio/key.py.
"""

from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field
from sqlmodel import Session

from clipforge.assets import update_asset
from clipforge.ffmpeg import FFmpegError
from clipforge.models import Asset
from clipforge.pipeline.loudnorm import measure_filter, measure_loudness
from clipforge.pipeline.step import StepError
from clipforge.proedit.audio.key import musical_key
from clipforge.proedit.beats import (
    SAMPLE_RATE,
    Samples,
    grid_of_samples,
    read_samples,
)

CATEGORIES = ("whoosh", "impact", "riser", "click", "chime", "music", "other")
MOODS = ("calm", "medium", "intense")
AudioKind = Literal["sfx", "music", "audio"]
FRAME = 512
HOP = 128
ATTACK_FRAMES = 4
ATTACK_TOP_DB = 20.0
ATTACK_FLOOR_DB = 40.0
SHARP_RISE_DB = 20.0
SHARP = 0.6
CLICK_S = 0.25
EARLY_PEAK = 0.3
LATE_PEAK = 0.6
WHOOSH_PEAK = (0.12, 0.88)
RISER_GAIN = 3.0
RISER_MIN_S = 0.8
CHIME_FLATNESS = 0.05
CHIME_CENTROID_HZ = 1200.0
MAX_SOUND_S = 8.0
MUSIC_MIN_S = 8.0
MIN_LOUDNESS_S = 0.4
LOUDNESS_TARGET = -14.0
MIN_BEAT_S = 4.0
MIN_KEY_S = 4.0
ATTACK_TAG = {True: "sharp-attack", False: "soft-attack"}
DECIMALS = 3


class AudioTags(BaseModel):
    """What analyze_audio finds in a file. bpm and key are None for a sound
    that is not music or where none was found; loudness_lufs is None for a
    sound shorter than MIN_LOUDNESS_S or for silence. energy_curve holds one
    value (0 to 1) per second, the last for the part second."""

    duration_s: float = Field(ge=0)
    bpm: float | None = Field(default=None, gt=0)
    key: str | None = None
    loudness_lufs: float | None = None
    energy_curve: list[float]
    onset_sharpness: float = Field(ge=0, le=1)
    category: str
    mood: str

    @property
    def sharp(self) -> bool:
        """Whether the sound reaches its peak fast (onset_sharpness >= SHARP)."""
        return self.onset_sharpness >= SHARP


def analyze_audio(path: Path, kind: AudioKind = "audio") -> AudioTags:
    """Return the tags of the audio file path.

    kind "music" makes it music, "sfx" a sound, "audio" music when it lasts
    at least MUSIC_MIN_S. Raises StepError if ffmpeg cannot decode it.
    """
    samples = read_samples(path)
    duration = len(samples) / SAMPLE_RATE
    is_music = kind == "music" or (kind == "audio" and duration >= MUSIC_MIN_S)
    padded = np.concatenate([np.zeros(FRAME, np.float32), samples])
    rms = _rms(padded)
    db = _db(rms)
    sharpness = onset_sharpness(db)
    centroid, flatness = _spectrum(padded, rms)
    grid = grid_of_samples(samples, SAMPLE_RATE) if duration >= MIN_BEAT_S else None
    bpm = grid.bpm if is_music and grid is not None else None
    loudness = _loudness(path, duration)
    category = (
        "music" if is_music else _category(rms, duration, sharpness, centroid, flatness)
    )
    return AudioTags(
        duration_s=round(duration, DECIMALS),
        bpm=bpm,
        key=musical_key(samples) if is_music and duration >= MIN_KEY_S else None,
        loudness_lufs=loudness,
        energy_curve=energy_curve(samples),
        onset_sharpness=round(sharpness, DECIMALS),
        category=category,
        mood=_mood(db, centroid, bpm),
    )


def onset_sharpness(db: npt.NDArray[np.float64]) -> float:
    """Return the onset sharpness (module doc) of a frame level curve in dB."""
    if len(db) <= ATTACK_FRAMES:
        return 0.0
    peak = float(db.max())
    ends = db[ATTACK_FRAMES:]
    starts = np.maximum(db[:-ATTACK_FRAMES], peak - ATTACK_FLOOR_DB)
    rises = np.where(ends >= peak - ATTACK_TOP_DB, ends - starts, 0.0)
    return float(min(max(rises.max(), 0.0) / SHARP_RISE_DB, 1.0))


def energy_curve(samples: Samples, rate: int = SAMPLE_RATE) -> list[float]:
    """Return the RMS of each second of samples (the last may be partial),
    as a share of the loudest second; all 0 for silence."""
    if len(samples) == 0:
        return [0.0]
    seconds = [samples[i : i + rate] for i in range(0, len(samples), rate)]
    levels = np.array([np.sqrt(np.mean(s.astype(np.float64) ** 2)) for s in seconds])
    top = float(levels.max())
    scaled = levels / top if top > 1e-9 else np.zeros_like(levels)
    return [round(float(v), DECIMALS) for v in scaled]


def tag_names(tags: AudioTags) -> list[str]:
    """Return the asset tags that tags stand for: its category, mood and
    attack (the asset has no field for the onset sharpness)."""
    return [tags.category, tags.mood, ATTACK_TAG[tags.sharp]]


def tag_asset(session: Session, asset: Asset, *, category: str | None = None) -> Asset:
    """Analyze the file of asset and store the result on it: bpm, key,
    loudness, energy curve, category (category if given, else the found one),
    mood and the tags of tag_names added to its tags. Raises StepError if the
    file cannot be decoded; the asset is unchanged then."""
    kind: AudioKind = "audio"
    if asset.kind == "sfx" or asset.kind == "music":
        kind = asset.kind
    found = analyze_audio(Path(asset.path), kind)
    chosen = category or asset.category or found.category
    named = [*tag_names(found.model_copy(update={"category": chosen}))]
    return update_asset(
        session,
        asset.id,
        bpm=found.bpm,
        key=found.key,
        loudness_lufs=found.loudness_lufs,
        energy_curve=found.energy_curve,
        category=chosen,
        mood=found.mood,
        tags=list(dict.fromkeys([*asset.tags, *named])),
    )


def _rms(padded: Samples) -> npt.NDArray[np.float64]:
    """Return the RMS of each frame (FRAME samples every HOP) of padded, the
    samples after FRAME zeros (so that an attack at the start is a rise)."""
    import librosa

    if len(padded) <= FRAME:
        return np.zeros(1)
    frames = librosa.feature.rms(
        y=padded, frame_length=FRAME, hop_length=HOP, center=False
    )[0]
    return np.asarray(frames, dtype=np.float64)


def _db(rms: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Return rms in dB of full scale, silence at -120."""
    return np.asarray(20 * np.log10(np.maximum(rms, 1e-6)), dtype=np.float64)


def _spectrum(padded: Samples, rms: npt.NDArray[np.float64]) -> tuple[float, float]:
    """Return the spectral centroid (Hz) and flatness of the loud frames of
    padded (those within 20 dB of the loudest), 0 and 1 for silence."""
    import librosa

    if len(padded) <= FRAME or float(rms.max()) < 1e-4:
        return 0.0, 1.0
    centroid = librosa.feature.spectral_centroid(
        y=padded, sr=SAMPLE_RATE, n_fft=FRAME, hop_length=HOP, center=False
    )[0]
    flatness = librosa.feature.spectral_flatness(
        y=padded, n_fft=FRAME, hop_length=HOP, center=False
    )[0]
    loud = rms >= rms.max() * 0.1
    if not loud.any():
        return 0.0, 1.0
    return float(np.mean(centroid[loud])), float(np.mean(flatness[loud]))


def _third_energy(rms: npt.NDArray[np.float64]) -> tuple[float, float]:
    """Return the mean power of the first and the last third of rms."""
    third = max(len(rms) // 3, 1)
    power = rms**2
    return float(power[:third].mean()), float(power[-third:].mean())


def _category(
    rms: npt.NDArray[np.float64],
    duration: float,
    sharpness: float,
    centroid: float,
    flatness: float,
) -> str:
    """Return the category of a sound (module doc)."""
    if float(rms.max()) < 1e-4:
        return "other"
    peak_at = int(np.argmax(rms)) / max(len(rms) - 1, 1)
    first, last = _third_energy(rms)
    if sharpness >= SHARP:
        if duration < CLICK_S:
            return "click"
        if flatness < CHIME_FLATNESS and centroid >= CHIME_CENTROID_HZ:
            return "chime"
        return "impact" if peak_at <= EARLY_PEAK else "other"
    if (
        duration >= RISER_MIN_S
        and peak_at >= LATE_PEAK
        and last >= RISER_GAIN * max(first, 1e-12)
    ):
        return "riser"
    if WHOOSH_PEAK[0] <= peak_at <= WHOOSH_PEAK[1]:
        return "whoosh"
    return "other"


def _mood(db: npt.NDArray[np.float64], centroid: float, bpm: float | None) -> str:
    """Return the energy class of a sound: the mean of its loudness (-40 to
    -10 dBFS RMS of the loud frames), brightness (500 to 4000 Hz) and, for
    music, tempo (60 to 160 BPM), each as 0 to 1."""
    loud = db[db >= db.max() - 20.0]
    scores = [
        _unit((float(loud.mean()) + 40.0) / 30.0),
        _unit((centroid - 500.0) / 3500.0),
    ]
    if bpm is not None:
        scores.append(_unit((bpm - 60.0) / 100.0))
    level = float(np.mean(scores))
    return MOODS[0] if level < 0.35 else MOODS[1] if level < 0.6 else MOODS[2]


def _unit(value: float) -> float:
    """Return value limited to 0..1."""
    return min(max(value, 0.0), 1.0)


def _loudness(path: Path, duration: float) -> float | None:
    """Return the integrated loudness (LUFS) of path, None if it is shorter
    than MIN_LOUDNESS_S, silent or loudnorm cannot measure it."""
    if duration < MIN_LOUDNESS_S:
        return None
    graph = f"[0:a:0]{measure_filter(LOUDNESS_TARGET)}[m]"
    try:
        measured = measure_loudness(["-i", path], graph, "[m]")
    except FFmpegError as exc:
        raise StepError(f"cannot measure the loudness of {path}: {exc}") from exc
    return None if measured is None else round(measured.integrated, 1)
