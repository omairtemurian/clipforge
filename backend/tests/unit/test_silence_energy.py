"""Tests of the silences and energy peaks (SPEC 6.3) of pipeline/level_events.

The audio is made with numpy and measured with loudness.rms_db, as the
signals step measures a job's audio.wav. Noise has a fixed seed, so every
run hears the same samples.
"""

import numpy as np
import numpy.typing as npt
import pytest
from clipforge.pipeline.level_events import (
    energy_peaks,
    frame_runs,
    rolling_z_scores,
    silences,
)
from clipforge.pipeline.loudness import Envelope, rms_db
from clipforge.pipeline.signal_merge import ScoredSpan

RATE = 16000
TOLERANCE_S = 0.05

Samples = npt.NDArray[np.float32]


def tone(seconds: float, amplitude: float = 0.3) -> Samples:
    """Return seconds of a 440 Hz sine wave of amplitude."""
    time = np.arange(round(seconds * RATE)) / RATE
    return (amplitude * np.sin(2 * np.pi * 440 * time)).astype(np.float32)


def pause(seconds: float) -> Samples:
    """Return seconds of digital silence."""
    return np.zeros(round(seconds * RATE), dtype=np.float32)


def noise(seconds: float, rms: float, seed: int = 0) -> Samples:
    """Return seconds of white noise whose RMS is about rms."""
    rng = np.random.default_rng(seed)
    return (rms * rng.standard_normal(round(seconds * RATE))).astype(np.float32)


def syllables(seconds: float, seed: int = 0) -> Samples:
    """Return seconds of speech-like sound: bursts of noise of 0.12-0.35 s at
    random levels, with pauses of 0.03-0.2 s between them."""
    rng = np.random.default_rng(seed)
    parts: list[Samples] = []
    while sum(map(len, parts)) < seconds * RATE:
        level = rng.uniform(0.03, 0.08)
        parts.append(noise(rng.uniform(0.12, 0.35), level, int(rng.integers(1000))))
        parts.append(pause(rng.uniform(0.03, 0.2)))
    return np.concatenate(parts)[: round(seconds * RATE)]


def measure(*parts: Samples, start: float = 0.0) -> tuple[Envelope, float]:
    """Return the envelope of parts played one after another from source time
    start, and the time at which they end."""
    samples = np.concatenate(parts)
    return Envelope(start, rms_db(samples)), start + len(samples) / RATE


def times(spans: list[ScoredSpan]) -> list[tuple[float, float]]:
    """Return the (start, end) of each span, checking that its score is 1."""
    assert all(span.score == 1.0 for span in spans)
    return [(span.start, span.end) for span in spans]


def near(start: float, end: float) -> tuple[float, float]:
    """Return (start, end) to compare with a span's within TOLERANCE_S."""
    return (
        pytest.approx(start, abs=TOLERANCE_S),
        pytest.approx(end, abs=TOLERANCE_S),
    )


def test_a_half_second_pause_between_two_tones_is_one_silence() -> None:
    envelope, end = measure(tone(1.0), pause(0.5), tone(1.0))
    assert times(silences(envelope, end)) == [near(1.0, 1.5)]
    assert energy_peaks(envelope, end) == []


def test_a_pause_shorter_than_0_35_s_is_no_silence() -> None:
    envelope, end = measure(tone(1.0), pause(0.3), tone(1.0))
    assert silences(envelope, end) == []


@pytest.mark.parametrize(("amplitude", "found"), [(0.01, 1), (0.02, 0)])
def test_sound_below_minus_40_dbfs_is_silence(amplitude: float, found: int) -> None:
    # A tone of amplitude 0.01 is at -43 dBFS; one of 0.02 is at -37 dBFS.
    envelope, end = measure(tone(1.0), tone(0.5, amplitude), tone(1.0))
    assert len(silences(envelope, end)) == found


def test_silences_at_the_ends_reach_the_ends_of_the_audio() -> None:
    envelope, end = measure(pause(0.5), tone(1.0), pause(0.5), start=10.0)
    first, last = silences(envelope, end)
    assert (first.start, last.end) == (10.0, 12.0)
    assert (first.end, last.start) == near(10.5, 11.5)


@pytest.mark.parametrize(
    "background", [noise(25.0, 0.02), syllables(25.0)], ids=["noise", "speech"]
)
def test_a_loud_burst_is_one_energy_peak(background: Samples) -> None:
    # The burst is 1.5 s of noise, 14-20 dB louder than the sound around it.
    burst = noise(1.5, 0.2, seed=1)
    envelope, end = measure(background, burst, background[: 4 * RATE])
    assert times(energy_peaks(envelope, end)) == [near(25.0, 26.5)]


@pytest.mark.parametrize(
    "steady",
    [noise(30.0, 0.05), syllables(60.0), tone(30.0), pause(30.0)],
    ids=["noise", "speech", "tone", "silence"],
)
def test_steady_sound_has_no_energy_peaks(steady: Samples) -> None:
    envelope, end = measure(steady)
    assert energy_peaks(envelope, end) == []


def test_a_burst_too_quiet_to_hear_is_no_energy_peak() -> None:
    # Noise at -46 dBFS in digital silence: its z-score is high, but it is
    # silent all the same.
    envelope, end = measure(pause(10.0), noise(1.0, 0.005), pause(10.0))
    assert energy_peaks(envelope, end) == []


def test_bursts_up_to_half_a_second_apart_are_one_energy_peak() -> None:
    quiet, loud = noise(10.0, 0.02), noise(0.6, 0.2, seed=1)
    envelope, end = measure(quiet, loud, quiet[: RATE * 3 // 10], loud, quiet)
    assert times(energy_peaks(envelope, end)) == [near(10.0, 11.5)]

    envelope, end = measure(quiet, loud, quiet[:RATE], loud, quiet)
    assert times(energy_peaks(envelope, end)) == [near(10.0, 10.6), near(11.6, 12.2)]


def test_a_burst_shorter_than_0_2_s_is_no_energy_peak() -> None:
    quiet = noise(10.0, 0.02)
    envelope, end = measure(quiet, noise(0.1, 0.2, seed=1), quiet)
    assert energy_peaks(envelope, end) == []


def test_no_audio_has_no_silences_or_energy_peaks() -> None:
    envelope = Envelope(5.0, np.zeros(0, dtype=np.float32))
    assert silences(envelope, 5.0) == energy_peaks(envelope, 5.0) == []


def test_rolling_z_scores_use_the_values_around_each_one() -> None:
    mean, z_scores = rolling_z_scores(np.array([0.0, 0.0, 0.0, 0.0, 10.0]), 1)
    np.testing.assert_allclose(mean, [0.0, 0.0, 0.0, 10 / 3, 5.0])
    np.testing.assert_allclose(z_scores, [0.0, 0.0, 0.0, -(0.5**0.5), 1.0])


def test_frame_runs_tile_the_audio() -> None:
    envelope = Envelope(2.0, np.zeros(6, dtype=np.float32))
    mask = np.array([True, False, True, True, False, True])
    assert times(frame_runs(envelope, mask, 2.07)) == [
        pytest.approx((2.0, 2.0175)),
        pytest.approx((2.0275, 2.0475)),
        pytest.approx((2.0575, 2.07)),
    ]
    assert times(frame_runs(envelope, np.ones(6, dtype=np.bool_), 2.07)) == [
        (2.0, 2.07)
    ]
    assert frame_runs(envelope, np.zeros(6, dtype=np.bool_), 2.07) == []
