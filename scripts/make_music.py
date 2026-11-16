"""Synthesize ClipForge's bundled background music (assets/music).

Every track is an original composition made here from sine waves and
seeded noise: no recording or third-party sample is used, so the tracks are
dedicated to the public domain (CC0 1.0; assets/music/LICENSES.md). Each one
is a whole number of bars and loops without a seam (notes that ring past
the end wrap around to its start), so the render can loop it under a long
clip. Run from the repo root (rebuilds the same files):

    uv run --project backend python scripts/make_music.py

The samples are written as 48 kHz mono 16-bit FLAC with ffmpeg.
"""

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

RATE = 48000
OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "music"
TARGET_RMS_DB = -20.0
PEAK_LIMIT = 0.89  # -1 dBFS

Wave = NDArray[np.float64]


def freq(midi: float) -> float:
    """Return the frequency in Hz of MIDI note midi (69 = A4 = 440 Hz)."""
    return 440.0 * 2 ** ((midi - 69) / 12)


def times(seconds: float) -> Wave:
    """Return the sample times of seconds of sound."""
    return np.arange(int(seconds * RATE)) / RATE


def adsr(n: int, attack: float, release: float) -> Wave:
    """Return an envelope of n samples: a linear attack, then held, then a
    linear release (seconds)."""
    env = np.ones(n)
    a, r = min(int(attack * RATE), n), min(int(release * RATE), n)
    if a:
        env[:a] = np.linspace(0, 1, a)
    if r:
        env[n - r :] *= np.linspace(1, 0, r)
    return env


def pluck(midi: float, seconds: float, decay: float = 4.0) -> Wave:
    """A plucked note: a few harmonics that fade quicker the higher they are."""
    t = times(seconds)
    f = freq(midi)
    tone = sum(
        np.sin(2 * np.pi * f * k * t) * np.exp(-decay * k * t) / k for k in (1, 2, 3, 4)
    )
    return tone * adsr(len(t), 0.004, 0.05)


def pad(midi: float, seconds: float, attack: float = 0.6) -> Wave:
    """A soft pad note: three slightly detuned sines with a slow attack."""
    t = times(seconds)
    f = freq(midi)
    tone = sum(np.sin(2 * np.pi * f * d * t) for d in (0.997, 1.0, 1.003)) / 3
    tone += 0.15 * np.sin(2 * np.pi * 2 * f * t)
    return tone * adsr(len(t), attack, min(attack, seconds / 2))


def keys(midi: float, seconds: float) -> Wave:
    """An electric-piano-like note: a sine and a quick bright overtone."""
    t = times(seconds)
    f = freq(midi)
    tone = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 4 * f * t) * np.exp(
        -12 * t
    )
    return tone * np.exp(-1.6 * t) * adsr(len(t), 0.005, 0.08)


def bell(midi: float, seconds: float) -> Wave:
    """A soft bell: a sine with an inharmonic partial, slowly fading."""
    t = times(seconds)
    f = freq(midi)
    tone = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(
        -3 * t
    )
    return tone * np.exp(-2.2 * t) * adsr(len(t), 0.003, 0.1)


def bass(midi: float, seconds: float, harmonics: int = 3) -> Wave:
    """A bass note: a few saw-like harmonics with a short fade."""
    t = times(seconds)
    f = freq(midi)
    tone = sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, harmonics + 1))
    return tone * np.exp(-3 * t) * adsr(len(t), 0.005, 0.03)


def kick(seconds: float = 0.35) -> Wave:
    """A kick drum: a sine falling from 120 to 45 Hz, fading fast."""
    t = times(seconds)
    pitch = 45 + 75 * np.exp(-30 * t)
    phase = 2 * np.pi * np.cumsum(pitch) / RATE
    return np.sin(phase) * np.exp(-9 * t)


def noise_hit(
    rng: np.random.Generator, seconds: float, decay: float, bright: bool
) -> Wave:
    """A hat (bright) or clap/snare burst: seeded white noise, fading."""
    t = times(seconds)
    noise = rng.uniform(-1, 1, len(t))
    if bright:
        noise = np.diff(noise, prepend=0.0) / 2
    else:
        noise = np.convolve(noise, np.ones(4) / 4, mode="same")
    return noise * np.exp(-decay * t)


@dataclass
class Track:
    """A loop of bars bars of beats_per_bar beats at bpm, being written."""

    bpm: float
    bars: int
    beats_per_bar: int = 4

    def __post_init__(self) -> None:
        self.beat = 60.0 / self.bpm
        self.length = int(round(self.bars * self.beats_per_bar * self.beat * RATE))
        self.buffer = np.zeros(self.length)

    def add(self, at_beat: float, sound: Wave, gain: float) -> None:
        """Add sound from beat at_beat, wrapping past the loop's end."""
        start = int(round(at_beat * self.beat * RATE))
        index = (start + np.arange(len(sound))) % self.length
        np.add.at(self.buffer, index, sound * gain)


def finish(buffer: Wave) -> Wave:
    """Return buffer at TARGET_RMS_DB RMS, softly limited under PEAK_LIMIT."""
    rms = float(np.sqrt(np.mean(buffer**2)))
    scaled = buffer * (10 ** (TARGET_RMS_DB / 20) / rms)
    return np.tanh(scaled / PEAK_LIMIT) * PEAK_LIMIT


def chord_loop(
    track: Track,
    chords: Sequence[Sequence[int]],
    bars_per_chord: int,
    voice: Callable[[Track, int, Sequence[int]], None],
) -> None:
    """Call voice(track, bar, chord) for every bar, with the chords in turn."""
    for bar in range(track.bars):
        voice(track, bar, chords[(bar // bars_per_chord) % len(chords)])


def bright_steps() -> Wave:
    """Upbeat pop loop, 120 bpm, C G Am F: kick, clap, hats, bass, plucks."""
    track, rng = Track(120, 16), np.random.default_rng(11)
    chords = [(60, 64, 67), (55, 59, 62), (57, 60, 64), (53, 57, 60)]
    melody = [72, 74, 76, 79, 76, 74, 72, 71]

    def voice(t: Track, bar: int, chord: Sequence[int]) -> None:
        base = bar * 4
        for beat in range(4):
            t.add(base + beat, kick(), 0.9 if beat % 2 == 0 else 0.0)
            if beat % 2:
                t.add(base + beat, noise_hit(rng, 0.2, 18, False), 0.35)
        for eighth in range(8):
            t.add(base + eighth / 2, noise_hit(rng, 0.05, 60, True), 0.25)
            t.add(base + eighth / 2, bass(chord[0] - 24, 0.24), 0.45)
            note = chord[eighth % 3] + 12
            t.add(base + eighth / 2, pluck(note, 0.45), 0.22)
        if bar >= 8:
            for step, note in enumerate(melody[(bar % 2) * 4 : (bar % 2) * 4 + 4]):
                t.add(base + step, bell(note, 0.9), 0.25)

    chord_loop(track, chords, 1, voice)
    return finish(track.buffer)


def slow_tide() -> Wave:
    """Calm ambient loop, 72 bpm, Dmaj7 Bm7 Gmaj7 A: pads, bells, sub bass."""
    track = Track(72, 8)
    chords = [(62, 66, 69, 73), (59, 62, 66, 69), (55, 59, 62, 66), (57, 61, 64, 69)]

    def voice(t: Track, bar: int, chord: Sequence[int]) -> None:
        base = bar * 4
        for note in chord:
            t.add(base, pad(note, 4 * t.beat + 0.6, attack=0.9), 0.18)
        t.add(base, pad(chord[0] - 24, 4 * t.beat, attack=0.4), 0.35)
        for beat, index in enumerate((3, 2, 1, 2)):
            t.add(base + beat + 0.5, bell(chord[index] + 12, 1.6), 0.12)

    chord_loop(track, chords, 1, voice)
    return finish(track.buffer)


def night_drive() -> Wave:
    """Driving minor loop, 100 bpm, Am F C G: pulsing bass, four-on-the-floor
    kick, snare, an arpeggio lead in the second half."""
    track, rng = Track(100, 16), np.random.default_rng(23)
    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]

    def voice(t: Track, bar: int, chord: Sequence[int]) -> None:
        base = bar * 4
        for beat in range(4):
            t.add(base + beat, kick(0.3), 0.85)
            if beat % 2:
                t.add(base + beat, noise_hit(rng, 0.25, 14, False), 0.4)
        for sixteenth in range(16):
            at = base + sixteenth / 4
            t.add(at, bass(chord[0] - 12, 0.14, harmonics=6), 0.3)
            t.add(at, noise_hit(rng, 0.03, 90, True), 0.12)
        for chord_note in chord:
            t.add(base, pad(chord_note, 4 * t.beat, attack=0.2), 0.08)
        if bar >= 8:
            for step in range(8):
                note = chord[(step * 2) % 3] + 12 + (12 if step % 4 == 3 else 0)
                t.add(base + step / 2, pluck(note, 0.35, decay=6), 0.18)

    chord_loop(track, chords, 2, voice)
    return finish(track.buffer)


def paper_lanterns() -> Wave:
    """Chill lo-fi loop, 84 bpm with swing, Fmaj7 Em7 Dm7 Cmaj7: keys,
    soft kick and rim, a walking bass."""
    track, rng = Track(84, 8), np.random.default_rng(37)
    chords = [(53, 57, 60, 64), (52, 55, 59, 62), (50, 53, 57, 60), (48, 52, 55, 59)]
    swing = 0.58

    def voice(t: Track, bar: int, chord: Sequence[int]) -> None:
        base = bar * 4
        for note in chord:
            t.add(base, keys(note, 2.5), 0.16)
            t.add(base + 2 + swing, keys(note + 12, 1.2), 0.07)
        t.add(base, kick(0.4), 0.7)
        t.add(base + 2.5, kick(0.4), 0.5)
        for beat in (1, 3):
            t.add(base + beat, noise_hit(rng, 0.08, 40, True), 0.3)
        for eighth in range(8):
            offset = eighth // 2 + (swing if eighth % 2 else 0)
            t.add(base + offset, noise_hit(rng, 0.04, 80, True), 0.1)
        for beat, index in enumerate((0, 2, 1, 3)):
            t.add(base + beat, bass(chord[index] - 24, 0.6), 0.35)

    chord_loop(track, chords, 1, voice)
    return finish(track.buffer)


TRACKS: dict[str, Callable[[], Wave]] = {
    "bright_steps.flac": bright_steps,
    "slow_tide.flac": slow_tide,
    "night_drive.flac": night_drive,
    "paper_lanterns.flac": paper_lanterns,
}


def write_flac(samples: Wave, path: Path) -> None:
    """Write samples as 48 kHz mono 16-bit FLAC (bit-exact) with ffmpeg."""
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(RATE)]
        + ["-ac", "1", "-i", "-", "-c:a", "flac", "-compression_level", "12"]
        + ["-fflags", "+bitexact", "-flags:a", "+bitexact", "-map_metadata", "-1"]
        + [str(path)],
        input=pcm,
        check=True,
    )


def main() -> None:
    """Write every track into OUT_DIR."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, make in TRACKS.items():
        path = OUT_DIR / name
        write_flac(make(), path)
        print(f"{path.name}: {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
