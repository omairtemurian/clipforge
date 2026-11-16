"""Generated style references with known audio features (tests only): a
music bed at a known tempo with a drop (optionally with a silence just
before it), noise-burst SFX between beats and spoken words (macOS `say`),
muxed under a still video. Times are seconds."""

import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt
from clipforge.ffmpeg import run_ffmpeg

RATE = 22050
BPM = 120
BEAT_S = 60 / BPM
DROP_BEAT = 16
DROP_S = DROP_BEAT * BEAT_S
QUIET = 0.1
GAP_S = 0.3
VOICE = "say"

Samples = npt.NDArray[np.float64]


def times(seconds: float) -> Samples:
    """The sample times of seconds of audio at RATE."""
    return np.arange(round(seconds * RATE)) / RATE


def bed(seconds: float, *, gap: bool = False) -> Samples:
    """A bed of a kick on every beat of BPM over a sustained A minor chord,
    at QUIET of its level until the drop at DROP_S (then full); with gap,
    silent for GAP_S right before the drop."""
    t = times(seconds)
    chord = sum(np.sin(2 * np.pi * f * t) for f in (220.0, 261.6, 329.6)) * 0.08
    kick_t = times(0.45)
    sweep = 55 * kick_t + 2 * (1 - np.exp(-30 * kick_t))
    kick = np.sin(2 * np.pi * sweep) * np.exp(-12 * kick_t)
    out = np.asarray(chord, dtype=np.float64)
    for k in range(int(seconds / BEAT_S)):
        start = round(k * BEAT_S * RATE)
        end = min(start + len(kick), len(out))
        out[start:end] += 0.6 * kick[: end - start]
    out[t < DROP_S] *= QUIET
    if gap:
        out[(t >= DROP_S - GAP_S) & (t < DROP_S)] = 0.0
    return out


def add_sfx(audio: Samples, at: list[float]) -> Samples:
    """audio with a 0.15 s noise burst (sharp attack, fast decay) at each
    time of at."""
    rng = np.random.default_rng(7)
    burst_t = times(0.15)
    burst = rng.uniform(-1, 1, len(burst_t)) * np.exp(-burst_t * 25) * 0.7
    out = audio.copy()
    for time in at:
        start = round(time * RATE)
        end = min(start + len(burst), len(out))
        out[start:end] += burst[: end - start]
    return out


def has_voice() -> bool:
    """Whether the `say` program is installed (macOS)."""
    return shutil.which(VOICE) is not None


def speech(folder: Path, text: str) -> Samples:
    """text spoken by `say`, at RATE."""
    spoken = folder / "speech.aiff"
    decoded = folder / "speech.wav"
    subprocess.run([VOICE, "-o", str(spoken), text], check=True)
    run_ffmpeg(["-i", spoken, "-ac", "1", "-ar", str(RATE), decoded])
    return read_wav(decoded)


def place(audio: Samples, part: Samples, at: float) -> Samples:
    """audio with part added from at seconds (cut at audio's end)."""
    out = audio.copy()
    start = round(at * RATE)
    end = min(start + len(part), len(out))
    out[start:end] += part[: end - start]
    return out


def read_wav(path: Path) -> Samples:
    """The samples (-1..1) of a mono 16-bit WAV file."""
    with wave.open(str(path), "rb") as wav:
        raw = wav.readframes(wav.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768


def write_wav(path: Path, audio: Samples) -> Path:
    """Write audio (mono, RATE) to path as 16-bit PCM; return path."""
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm.tobytes())
    return path


def reference(path: Path, audio: Samples) -> Path:
    """Write a reference with audio under a still 320x568 picture to path
    (h264 + AAC); return path."""
    sound = write_wav(path.with_suffix(".wav"), audio)
    seconds = len(audio) / RATE
    picture = f"color=c=0x304050:s=320x568:r=30:d={seconds:.3f}"
    run_ffmpeg(
        ["-f", "lavfi", "-i", picture, "-i", sound, "-c:v", "libx264"]
        + ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", path]
    )
    return path
