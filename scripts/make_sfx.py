"""Synthesize ClipForge's original sound effects (assets/sfx).

Every effect is made here from sine waves and seeded noise: no recording or
third-party sample is used, so they are dedicated to the public domain
(CC0 1.0; assets/sfx/LICENSES.md). The whooshes and the laugh of the pack
come from other sources (see LICENSES.md) and are not written by this
script. Run from the repo root (rebuilds the same files):

    uv run --project backend python scripts/make_sfx.py

The samples are written as 48 kHz mono 16-bit FLAC with ffmpeg.
"""

from collections.abc import Callable
from pathlib import Path

import numpy as np
from make_music import RATE, Wave, adsr, bell, kick, noise_hit, times, write_flac

OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "sfx"
PEAK = 0.7  # -3 dBFS


def sweep(start_hz: float, end_hz: float, seconds: float, curve: float) -> Wave:
    """A sine gliding from start_hz to end_hz over seconds (curve > 0 moves
    quickly at first, then slows)."""
    t = times(seconds)
    pitch = end_hz + (start_hz - end_hz) * np.exp(-curve * t / seconds)
    return np.sin(2 * np.pi * np.cumsum(pitch) / RATE)


def at_peak(samples: Wave) -> Wave:
    """Return samples scaled to peak at PEAK."""
    return samples * (PEAK / float(np.max(np.abs(samples))))


def pop() -> Wave:
    """A bubble pop: a sine falling from 1000 to 250 Hz in 0.15 s."""
    tone = sweep(1000, 250, 0.15, 12)
    return at_peak(tone * np.exp(-28 * times(0.15)) * adsr(len(tone), 0.001, 0.02))


def ding() -> Wave:
    """A bright bell strike on E6, ringing for 1 s."""
    return at_peak(bell(88, 1.0) * np.exp(-1.5 * times(1.0)))


def impact() -> Wave:
    """A deep boom: a falling sine under a short noise burst, 1.2 s."""
    t = times(1.2)
    rng = np.random.default_rng(5)
    body = sweep(95, 38, 1.2, 14) * np.exp(-3.2 * t)
    burst = noise_hit(rng, 1.2, 22, False)
    return at_peak(body * adsr(len(t), 0.002, 0.2) + 0.35 * burst)


def riser() -> Wave:
    """A tension riser: filtered noise and a sine rising for 1.5 s, then a
    short release."""
    t = times(1.6)
    rng = np.random.default_rng(9)
    rise = np.clip(t / 1.5, 0, 1) ** 2
    hiss = np.convolve(rng.uniform(-1, 1, len(t)), np.ones(3) / 3, mode="same")
    tone = np.sin(2 * np.pi * np.cumsum(220 + 1540 * rise) / RATE)
    return at_peak((0.6 * hiss + 0.5 * tone) * rise * adsr(len(t), 0.01, 0.1))


def tick() -> Wave:
    """A short click: 40 ms of a damped 2.4 kHz sine."""
    t = times(0.06)
    return at_peak(np.sin(2 * np.pi * 2400 * t) * np.exp(-110 * t))


def sparkle() -> Wave:
    """A rising chime: five high bells a 16th apart, ringing out, 1.3 s."""
    out = np.zeros(int(1.3 * RATE))
    for step, note in enumerate((84, 88, 91, 96, 100)):
        start = int(step * 0.07 * RATE)
        sound = bell(note, 0.9) * (0.55 + 0.1 * step)
        out[start : start + len(sound)] += sound[: len(out) - start]
    return at_peak(out)


def badum_tss() -> Wave:
    """A rimshot: two drum hits and a cymbal crash, 1.4 s."""
    rng = np.random.default_rng(13)
    out = np.zeros(int(1.4 * RATE))
    for at, gain in ((0.0, 0.8), (0.16, 1.0)):
        start = int(at * RATE)
        hit = kick(0.3) * gain + noise_hit(rng, 0.3, 30, False) * 0.5
        out[start : start + len(hit)] += hit
    start = int(0.38 * RATE)
    crash = noise_hit(rng, 1.0, 5, True)
    out[start : start + len(crash)] += crash * 0.6
    return at_peak(out)


EFFECTS: dict[str, Callable[[], Wave]] = {
    "pop_bubble.flac": pop,
    "ding_bell.flac": ding,
    "impact_boom.flac": impact,
    "riser_swell.flac": riser,
    "tick_click.flac": tick,
    "sparkle_chime.flac": sparkle,
    "rimshot_badum.flac": badum_tss,
}


def main() -> None:
    """Write every effect into OUT_DIR."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, make in EFFECTS.items():
        path = OUT_DIR / name
        write_flac(make(), path)
        print(f"{path.name}: {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
