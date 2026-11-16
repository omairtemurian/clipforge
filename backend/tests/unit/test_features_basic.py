"""Music beat grid and the shared edit feature extractors (TASK-206, SPEC-v3
3.2/4.3) on ffmpeg-made fixtures (tests/feature_fixtures.py) with known
values.

Tolerances (docs/decisions.md): beats ±20 ms, BPM ±1, drops ±20 ms; cut,
flash and B&W edges ±1 frame (1/30 s); zoom edges ±2 frames, zoom scale
±0.02; shake edges ±0.2 s, shake amplitude ±0.005 frame widths; frame luma
±0.02.
"""

from collections.abc import Callable
from pathlib import Path

import cv2
import feature_fixtures as fx
import numpy as np
import pytest
from clipforge.pipeline.frame_stream import stream_frames
from clipforge.proedit import beats
from clipforge.proedit.features import cuts, flashes, motion
from clipforge.proedit.features.color import (
    BW_SATURATION,
    FrameColor,
    color_stats,
    frame_color,
)
from clipforge.proedit.features.motion import PairMotion
from clipforge.proedit.features.video import VideoFeatures, measure_video

FRAME = 1 / fx.FPS
BEAT_TOLERANCE = 0.02


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], Path]:
    """Return a maker of the named fixture (feature_fixtures.make_<name>),
    each written once per module."""
    folder = tmp_path_factory.mktemp("features")
    cache: dict[str, Path] = {}

    def make(name: str) -> Path:
        if name not in cache:
            cache[name] = getattr(fx, f"make_{name}")(folder / f"{name}.mp4")
        return cache[name]

    return make


@pytest.fixture(scope="module")
def measured(made: Callable[[str], Path]) -> Callable[[str], VideoFeatures]:
    """Return the features of the named fixture video, measured once."""
    cache: dict[str, VideoFeatures] = {}

    def measure(name: str) -> VideoFeatures:
        if name not in cache:
            cache[name] = measure_video(made(name))
        return cache[name]

    return measure


# Beat grid


@pytest.mark.parametrize("bpm", [120, 150])
def test_the_beat_grid_of_a_click_track(tmp_path: Path, bpm: int) -> None:
    grid = beats.music_grid(fx.make_click_track(tmp_path / "click.m4a", bpm))
    period = 60 / bpm
    expected = np.arange(0, 16 - 1e-9, period)
    assert grid.bpm == pytest.approx(bpm, abs=1)
    assert len(grid.beats) == len(expected)
    assert np.abs(np.array(grid.beats) - expected).max() <= BEAT_TOLERANCE
    assert np.abs(np.array(grid.downbeats) - expected[::4]).max() <= BEAT_TOLERANCE
    assert grid.drops == [pytest.approx(16 * period, abs=BEAT_TOLERANCE)]
    assert grid.duration == pytest.approx(16, abs=0.05)


def test_audio_too_short_for_beats_has_no_grid() -> None:
    grid = beats.grid_of_samples(np.zeros(1000, np.float32), beats.SAMPLE_RATE)
    assert grid.duration == pytest.approx(1000 / beats.SAMPLE_RATE, abs=1e-4)
    assert (grid.bpm, grid.beats, grid.downbeats, grid.drops) == (None, [], [], [])


def test_downbeats_take_the_loudest_phase() -> None:
    times = [0.5 * k for k in range(12)]
    levels = [-20.0 if k % 4 == 2 else -30.0 for k in range(12)]
    assert beats.downbeats(times, levels) == [1.0, 3.0, 5.0]


def test_a_drop_needs_a_rise_to_the_loud_level() -> None:
    times = [0.5 * k for k in range(24)]
    quiet_then_loud = [-30.0] * 12 + [-10.0] * 12
    assert beats.drops(times, quiet_then_loud) == [6.0]
    small_rise = [-30.0] * 12 + [-26.0] * 12
    assert beats.drops(times, small_rise) == []


def test_beats_in_clip_time() -> None:
    times = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    assert beats.beats_in_clip(
        times, music_start=1.0, clip_duration=2.0, offset=0.5
    ) == [
        0.5,
        1.0,
        1.5,
    ]


# Cuts


def test_cuts_of_the_cut_fixture(measured: Callable[[str], VideoFeatures]) -> None:
    features = measured("cuts")
    assert features.cuts.cuts == pytest.approx(fx.CUTS, abs=FRAME)
    assert features.cuts.shot_lengths == pytest.approx(
        [1.0, 1.5, 0.4, 1.1, 1.0], abs=FRAME
    )
    assert features.cuts.mean_shot_s == pytest.approx(1.0, abs=0.01)
    assert features.cuts.cuts_per_second == [0, 1, 2, 0, 1]
    assert features.cuts.per_minute == pytest.approx(48, abs=0.1)
    # The white frame inside the fourth shot is a flash, not a cut.
    assert [f.start for f in features.flashes.flashes] == pytest.approx(
        [fx.CUT_FLASH_FRAME * FRAME], abs=FRAME
    )


def test_zooms_shakes_and_grades_are_not_cuts(
    measured: Callable[[str], VideoFeatures],
) -> None:
    for name in ("zoom", "shake", "flashes"):
        assert measured(name).cuts.cuts == [], name
    # The color fixture cuts only into and out of the red window, not at B&W.
    assert measured("color").cuts.cuts == pytest.approx(list(fx.RED_WINDOW), abs=FRAME)


def test_on_beat_share_and_mean_interval() -> None:
    grid = [0.0, 0.5, 1.0, 1.5]
    assert cuts.on_beat_share(
        [0.51, 1.03, 1.2], grid, tolerance=FRAME
    ) == pytest.approx(2 / 3, abs=1e-4)
    assert cuts.on_beat_share([], grid, tolerance=FRAME) == 0
    assert cuts.on_beat_share([1.0], [], tolerance=FRAME) == 0
    assert cuts.mean_interval([3.0, 1.0, 2.0, 2.0]) == 1.0
    assert cuts.mean_interval([1.0]) is None


# Motion


def test_zoom_ramp_and_punches(measured: Callable[[str], VideoFeatures]) -> None:
    zooms = measured("zoom").motion.zooms
    assert [z.kind for z in zooms] == ["ramp", "punch", "punch"]
    ramp, out, punch = zooms
    assert ramp.start == pytest.approx(31 * FRAME, abs=2 * FRAME)
    assert ramp.end == pytest.approx(61 * FRAME, abs=2 * FRAME)
    assert ramp.scale == pytest.approx(1.3, abs=0.02)
    assert out.start == pytest.approx(3.0, abs=FRAME)
    assert out.scale == pytest.approx(1 / 1.3, abs=0.02)
    assert punch.start == pytest.approx(4.0, abs=FRAME)
    assert punch.scale == pytest.approx(1.2, abs=0.02)
    assert measured("zoom").motion.shakes == []
    assert measured("zoom").motion.zooms_per_minute == pytest.approx(30, abs=0.1)


def test_shake_but_not_the_pan(measured: Callable[[str], VideoFeatures]) -> None:
    features = measured("shake")
    assert len(features.motion.shakes) == 1
    shake = features.motion.shakes[0]
    assert shake.start == pytest.approx(2.0, abs=0.2)
    assert shake.end == pytest.approx(3.0, abs=0.2)
    # 30 px of 1280 at 6 Hz: at most 30 * 2 pi * 6 / 30 px a frame.
    assert shake.amplitude == pytest.approx(30 * 2 * np.pi * 6 / 30 / 1280, abs=0.005)
    assert features.motion.zooms == []


def test_pair_motion_of_a_known_warp() -> None:
    rng = np.random.default_rng(7)
    texture = (rng.random((180, 320)) * 255).astype(np.uint8)
    texture = np.asarray(cv2.GaussianBlur(texture, (5, 5), 1.5), np.uint8)
    matrix = cv2.getRotationMatrix2D((160, 90), 0, 1.1)
    matrix[0, 2] += 3.2
    zoomed = np.asarray(cv2.warpAffine(texture, matrix, (320, 180)), np.uint8)
    pair = motion.pair_motion(texture, zoomed)
    assert pair is not None
    assert pair.scale == pytest.approx(1.1, abs=0.005)
    assert pair.dx == pytest.approx(3.2 / 320, abs=0.002)
    assert pair.dy == pytest.approx(0, abs=0.002)
    assert motion.pair_motion(texture, np.zeros_like(texture)) is None


def test_zoom_and_shake_rules_on_given_pairs() -> None:
    still = PairMotion(scale=1.0, dx=0, dy=0)
    ramp = [PairMotion(scale=1.01, dx=0, dy=0)] * 10
    small = [PairMotion(scale=1.001, dx=0, dy=0)] * 30
    pairs = [None, still, *ramp, still, *small, PairMotion(scale=0.8, dx=0, dy=0)]
    events = motion.zoom_events(pairs, 30)
    assert [e.kind for e in events] == ["ramp", "punch"]
    assert [e.start for e in events] == pytest.approx([2 / 30, 43 / 30], abs=1e-4)
    assert [e.scale for e in events] == pytest.approx([1.01**10, 0.8], abs=1e-4)
    assert motion.scale_curve(pairs[:4]) == [1.0, 1.0, 1.01, pytest.approx(1.0201)]
    jolts = [PairMotion(scale=1, dx=0.01 * (-1) ** k, dy=0) for k in range(6)]
    pan = [PairMotion(scale=1, dx=0.01, dy=0)] * 6
    assert len(motion.shake_spans([None, *jolts], 30)) == 1
    assert motion.shake_spans([None, *pan], 30) == []


# Color


def test_bw_window_and_frame_colors(
    made: Callable[[str], Path], measured: Callable[[str], VideoFeatures]
) -> None:
    color = measured("color").color
    assert color.bw_share == pytest.approx(0.25, abs=FRAME / 6)
    assert len(color.bw_spans) == 1
    assert (color.bw_spans[0].start, color.bw_spans[0].end) == pytest.approx(
        fx.BW_WINDOW, abs=FRAME
    )
    frames = list(stream_frames(made("color"), 0, 180, (320, 180), fx.FPS))
    colored, gray, red = (
        frame_color(frames[30]),
        frame_color(frames[75]),
        frame_color(frames[120]),
    )
    assert gray.saturation < BW_SATURATION < colored.saturation
    assert gray.luma == pytest.approx(colored.luma, abs=0.02)
    assert red.luma == pytest.approx(0.299, abs=0.02)
    assert red.saturation > 0.9
    assert red.contrast < 0.02


def test_color_stats_sums_frames() -> None:
    frames = [
        FrameColor(luma=0.2, contrast=0.1, saturation=0.5),
        FrameColor(luma=0.4, contrast=0.3, saturation=0.0),
    ]
    stats = color_stats(frames, 2)
    assert (stats.mean_luma, stats.contrast, stats.saturation) == (0.3, 0.2, 0.25)
    assert stats.bw_share == 0.5
    assert [(s.start, s.end) for s in stats.bw_spans] == [(0.5, 1.0)]
    assert color_stats([], 30).bw_spans == []


# Flashes


def test_white_flashes_and_a_luma_spike(
    measured: Callable[[str], VideoFeatures],
) -> None:
    found = measured("flashes").flashes.flashes
    expected = [
        (45, 47, True),
        (120, 121, True),
        (fx.SPIKE_FRAME, fx.SPIKE_FRAME + 1, False),
    ]
    assert [f.start for f in found] == pytest.approx(
        [a * FRAME for a, _, _ in expected], abs=FRAME
    )
    assert [f.end for f in found] == pytest.approx(
        [b * FRAME for _, b, _ in expected], abs=FRAME
    )
    assert [f.white for f in found] == [white for _, _, white in expected]
    assert measured("flashes").flashes.per_minute == pytest.approx(30, abs=0.1)
    assert measured("flashes").motion.zooms == []


def test_a_long_bright_run_is_not_a_flash() -> None:
    dark = FrameColor(luma=0.2, contrast=0.1, saturation=0.3)
    white = FrameColor(luma=0.95, contrast=0.01, saturation=0.0)
    frames = [dark] * 10 + [white] * (flashes.MAX_FLASH_FRAMES + 1) + [dark] * 10
    assert flashes.detect_flashes(frames, 30).flashes == []
