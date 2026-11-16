"""Tests of the timeline's filmstrip and waveform (pipeline/preview_assets.py)."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.pipeline import preview_assets
from clipforge.pipeline.preview_assets import (
    MAX_TILES,
    PEAKS_PER_SECOND,
    TILE_HEIGHT,
    filmstrip,
    filmstrip_layout,
    peaks,
    waveform,
)


def test_a_filmstrip_has_a_tile_a_second_up_to_max_tiles() -> None:
    assert filmstrip_layout(10.0, 52.5) == (1.0, 43)
    assert filmstrip_layout(0.0, 0.0) == (1.0, 1)
    interval, count = filmstrip_layout(0.0, 600.0)
    assert (interval, count) == (600.0 / MAX_TILES, MAX_TILES)


def test_peaks_are_the_loudest_sample_of_each_bucket() -> None:
    rate = 1_000
    samples = np.zeros(rate, dtype="<i2")
    samples[5] = -16_384
    samples[25] = 32_767

    levels = peaks(samples, rate, 1.5)

    assert len(levels) == int(1.5 * PEAKS_PER_SECOND)
    assert levels[:2] == [0.5, 1.0]
    assert set(levels[2:]) == {0.0}


def test_filmstrip_is_one_row_of_tiles_and_cached(
    sample_mp4: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs: list[object] = []

    def spy(*args: object, **kwargs: object) -> object:
        runs.append(args)
        return run_ffmpeg(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(preview_assets, "run_ffmpeg", spy)

    strip = filmstrip(sample_mp4, tmp_path, "7", 50.0, 60.0)
    info = probe_media(strip.path)

    assert (strip.start, strip.interval, strip.count) == (50.0, 1.0, 10)
    assert info.height == TILE_HEIGHT and info.width == 10 * 160
    assert filmstrip(sample_mp4, tmp_path, "7", 50.0, 60.0) == strip
    assert len(runs) == 1

    other = filmstrip(sample_mp4, tmp_path, "7", 40.0, 60.0)
    assert list(tmp_path.iterdir()) == [other.path]


def test_waveform_of_a_silent_source_is_flat(sample_mp4: Path, tmp_path: Path) -> None:
    silent = tmp_path / "silent.mp4"
    run_ffmpeg(["-i", sample_mp4, "-t", "2", "-an", "-c:v", "copy", silent])

    wave = waveform(silent, tmp_path / "cache", "3", 0.0, 3.0)

    assert len(wave.peaks) == 3 * PEAKS_PER_SECOND
    assert set(wave.peaks) == {0.0}
