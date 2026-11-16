"""Tests of the RMS envelope of the job's audio (pipeline/loudness)."""

import math

import numpy as np
import pytest
from clipforge.pipeline.loudness import FLOOR_DB, Envelope, rms_db


def test_levels_are_the_rms_of_each_frame_in_dbfs() -> None:
    levels = rms_db(np.full(1200, 0.5, dtype=np.float32))
    assert levels.dtype == np.float32
    assert levels.tolist() == pytest.approx([20 * math.log10(0.5)] * 6, abs=1e-4)


def test_a_full_scale_sine_is_at_minus_3_db() -> None:
    # 1 kHz: each 400-sample frame holds exactly 25 periods.
    time = np.arange(16000) / 16000
    sine = np.sin(2 * np.pi * 1000 * time).astype(np.float32)
    assert rms_db(sine).tolist() == pytest.approx([-3.0103] * 98, abs=1e-3)


def test_digital_silence_is_at_the_floor() -> None:
    assert rms_db(np.zeros(800, dtype=np.float32)).tolist() == [FLOOR_DB] * 3


@pytest.mark.parametrize(
    ("samples", "frames"),
    [(0, 0), (399, 0), (400, 1), (559, 1), (560, 2), (16000, 98)],
)
def test_frames_that_would_run_past_the_end_are_left_out(
    samples: int, frames: int
) -> None:
    assert len(rms_db(np.zeros(samples, dtype=np.float32))) == frames


def test_frames_are_centered_12_5_ms_into_their_10_ms_hops() -> None:
    envelope = Envelope(10.0, np.arange(100, dtype=np.float32))
    assert envelope.between(10.0, 10.0125).tolist() == [0]
    assert envelope.between(10.02, 10.05).tolist() == [1, 2, 3]
    assert envelope.between(10.0225, 10.0425).tolist() == [1, 2, 3]
    assert envelope.between(11.0, 12.0).tolist() == [99]
    assert envelope.between(0.0, 9.0).tolist() == []
    assert envelope.between(12.0, 13.0).tolist() == []


def test_level_is_the_mean_power_of_the_frames_in_a_span() -> None:
    envelope = Envelope(0.0, np.array([-10, -20, -20, -10], dtype=np.float32))
    assert envelope.level(0.0, 0.025) == pytest.approx(10 * math.log10(0.055))
    assert envelope.level(0.0, 1.0) == pytest.approx(10 * math.log10(0.055))
    assert envelope.level(1.0, 2.0) is None


def test_baseline_is_the_median_level_of_the_window_around_a_time() -> None:
    # 10 s at -40 dB, then 5 s at -10 dB.
    levels = np.array([-40.0] * 1000 + [-10.0] * 500, dtype=np.float32)
    envelope = Envelope(0.0, levels)
    assert envelope.baseline(5.0, 10.0) == -40.0
    assert envelope.baseline(14.0, 2.0) == -10.0
    # 51 frames at -40 dB and 149 at -10 dB: the median, not the mean.
    assert envelope.baseline(10.5, 2.0) == -10.0
    # The window is cut at the ends of the audio: here it holds all 15 s.
    assert envelope.baseline(14.9, 30.0) == -40.0
    assert envelope.baseline(100.0, 30.0) is None
