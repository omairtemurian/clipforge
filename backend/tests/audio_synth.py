"""Generated sounds of the audio library tests (tests only): a click track, a
whoosh sweep, an impact, a riser, a chord progression and steady tones, written
as mono 16-bit WAV files."""

import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt

RATE = 22_050
Wave = npt.NDArray[np.float64]


def times(seconds: float) -> Wave:
    """Return the sample times of a sound of seconds."""
    return np.arange(int(seconds * RATE)) / RATE


def write_wav(path: Path, samples: Wave) -> Path:
    """Write samples (-1..1) as a mono 16-bit WAV at RATE; return path."""
    data = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(data.tobytes())
    return path


def click_track(bpm: float, seconds: float) -> Wave:
    """A click (5 ms of a damped 1.5 kHz sine) on every beat of bpm."""
    out = np.zeros(int(seconds * RATE))
    burst_t = times(0.02)
    burst = np.sin(2 * np.pi * 1500 * burst_t) * np.exp(-400 * burst_t)
    step = 60.0 / bpm
    for k in range(int(seconds / step)):
        start = int(k * step * RATE)
        end = min(start + len(burst), len(out))
        out[start:end] += 0.8 * burst[: end - start]
    return out


def whoosh(seconds: float = 0.8) -> Wave:
    """A sine sweeping from 300 to 3000 Hz under a smooth bell envelope."""
    t = times(seconds)
    pitch = 300 + 2700 * (t / seconds) ** 2
    envelope = np.sin(np.pi * t / seconds) ** 2
    return 0.7 * envelope * np.sin(2 * np.pi * np.cumsum(pitch) / RATE)


def impact(seconds: float = 1.2) -> Wave:
    """A boom: a 70 Hz sine and a noise burst with a 2 ms attack and a fall."""
    t = times(seconds)
    noise = np.random.default_rng(3).uniform(-1, 1, len(t))
    body = np.sin(2 * np.pi * 70 * t) * np.exp(-4 * t) + 0.4 * noise * np.exp(-30 * t)
    return 0.8 * body * np.minimum(t / 0.002, 1)


def riser(seconds: float = 2.0) -> Wave:
    """Noise that swells quadratically over seconds and then stops."""
    t = times(seconds)
    noise = np.random.default_rng(4).uniform(-1, 1, len(t))
    return 0.8 * noise * (t / seconds) ** 2


def tone(hz: float, seconds: float, amplitude: float = 0.1) -> Wave:
    """A steady sine."""
    return amplitude * np.sin(2 * np.pi * hz * times(seconds))


def chords(progression: list[tuple[int, ...]], seconds_each: float) -> Wave:
    """Triads of MIDI notes one after the other, each ringing out softly."""
    parts = []
    for notes in progression:
        t = times(seconds_each)
        chord = sum(np.sin(2 * np.pi * 440 * 2 ** ((n - 69) / 12) * t) for n in notes)
        parts.append(0.2 * chord * np.minimum(t / 0.05, 1))
    return np.concatenate(parts)


# I-IV-V-I in C major and the same in A minor (i-iv-v-i).
C_MAJOR = [(60, 64, 67), (65, 69, 72), (67, 71, 74), (60, 64, 67)]
A_MINOR = [(57, 60, 64), (62, 65, 69), (64, 67, 71), (57, 60, 64)]
