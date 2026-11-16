"""Video features of style references (TASK-229, SPEC-v3 4.3) on ffmpeg-made
references with known cuts, zooms, shakes, flashes, B&W, glitches,
vignette and grain (feature_fixtures, style_video_fixtures).

Tolerances (docs/decisions.md): cut, flash, B&W, split and spike edges ±1
frame; BPM ±1; zoom amplitude ±0.02, zoom duration ±2 frames; shake
duration ±0.4 s, shake amplitude ±0.005 frame widths; vignette strength
±0.03; grain ±15 % of the noise filter's sigma.
"""

import math
from collections.abc import Callable
from pathlib import Path

import feature_fixtures as fx
import pytest
import style_video_fixtures as sv
from clipforge.config import Settings
from clipforge.proedit.beats import MusicGrid
from clipforge.proedit.features.motion import PUNCH_FRAMES
from clipforge.proedit.style.analyze_video import (
    ReferenceVideoFeatures,
    analyze_video,
    rhythm_of,
)
from clipforge.proedit.style.store import measure_features

FRAME = 1 / fx.FPS
MAKERS: dict[str, Callable[[Path], Path]] = {
    "beat_cuts": sv.make_beat_cuts,
    "glitch": sv.make_glitch,
    "zoom": fx.make_zoom,
    "shake": fx.make_shake,
    "flashes": fx.make_flashes,
    "cuts": fx.make_cuts,
}


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], Path]:
    """Return a maker of the named reference video (MAKERS), each written
    once per module."""
    folder = tmp_path_factory.mktemp("references")
    cache: dict[str, Path] = {}

    def make(name: str) -> Path:
        if name not in cache:
            cache[name] = MAKERS[name](folder / f"{name}.mp4")
        return cache[name]

    return make


@pytest.fixture(scope="module")
def analyzed(made: Callable[[str], Path]) -> Callable[[str], ReferenceVideoFeatures]:
    """Return the features of the named reference video, analyzed once."""
    cache: dict[str, ReferenceVideoFeatures] = {}

    def analyze(name: str) -> ReferenceVideoFeatures:
        if name not in cache:
            cache[name] = analyze_video(made(name))
        return cache[name]

    return analyze


def test_the_cut_rhythm_follows_the_reference_s_own_beats(
    analyzed: Callable[[str], ReferenceVideoFeatures],
) -> None:
    features = analyzed("beat_cuts")
    assert features.video.cuts.cuts == pytest.approx(sv.BEAT_CUTS, abs=FRAME)
    rhythm = features.rhythm
    assert rhythm.cuts_per_second == [0, 1, 2, 1, 1, 0]
    assert rhythm.cuts_per_minute == pytest.approx(len(sv.BEAT_CUTS) / 6 * 60)
    assert rhythm.median_shot_s == pytest.approx(1.0, abs=FRAME)
    assert rhythm.bpm == pytest.approx(sv.BPM, abs=1)
    assert rhythm.cuts_on_beat == pytest.approx(4 / 5)
    assert rhythm.zooms_on_beat is None


def test_the_flash_and_the_black_and_white_shot_are_found(
    analyzed: Callable[[str], ReferenceVideoFeatures],
) -> None:
    video = analyzed("beat_cuts").video
    (flash,) = video.flashes.flashes
    assert flash.start == pytest.approx(sv.BEAT_FLASH_FRAME * FRAME, abs=FRAME)
    assert flash.white
    # The white flash frame has no color either.
    flash_bw, shot_bw = video.color.bw_spans
    assert flash_bw.start == pytest.approx(flash.start, abs=FRAME)
    assert (shot_bw.start, shot_bw.end) == pytest.approx(sv.BEAT_BW, abs=FRAME)
    bw_seconds = sv.BEAT_BW[1] - sv.BEAT_BW[0] + FRAME
    assert video.color.bw_share == pytest.approx(bw_seconds / 6, abs=2 * FRAME / 6)
    assert analyzed("beat_cuts").glitches.splits == []
    assert analyzed("beat_cuts").glitches.spikes == []


def test_zoom_punches_and_ramps_are_counted_with_their_amplitudes(
    analyzed: Callable[[str], ReferenceVideoFeatures],
) -> None:
    motion = analyzed("zoom").motion
    # Punches 1.3 -> 1.0 (0.3) and 1.0 -> 1.2 (0.2); a ramp 1.0 -> 1.3 in 1 s.
    assert motion.punches.count == 2
    assert motion.punches.per_minute == pytest.approx(20)
    assert motion.punches.amplitude == pytest.approx(0.25, abs=0.02)
    assert motion.punches.duration_s is not None
    assert motion.punches.duration_s <= PUNCH_FRAMES * FRAME
    assert motion.ramps.count == 1
    assert motion.ramps.amplitude == pytest.approx(0.3, abs=0.02)
    assert motion.ramps.duration_s == pytest.approx(1.0, abs=2 * FRAME)
    assert motion.shakes.count == 0
    assert motion.shakes.amplitude is None


def test_a_reference_without_audio_has_no_tempo(
    analyzed: Callable[[str], ReferenceVideoFeatures],
) -> None:
    rhythm = analyzed("zoom").rhythm
    assert rhythm.bpm is None and rhythm.cuts_on_beat is None
    assert rhythm.cuts_per_second == [0] * 6
    assert rhythm.median_shot_s == pytest.approx(6.0)


def test_zoom_starts_on_a_beat_are_counted(
    analyzed: Callable[[str], ReferenceVideoFeatures],
) -> None:
    video = analyzed("zoom").video
    # The punches start at 3.0 and 4.0 s, the ramp at about 1.0 s.
    grid = MusicGrid(duration=6, bpm=120, beats=[0.5, 3.0, 4.0, 5.5])
    rhythm = rhythm_of(video, grid)
    assert rhythm.bpm == 120
    assert rhythm.zooms_on_beat == pytest.approx(2 / 3, abs=1e-4)
    assert rhythm.cuts_on_beat is None


def test_a_shake_is_counted_with_its_amplitude(
    analyzed: Callable[[str], ReferenceVideoFeatures],
) -> None:
    shakes = analyzed("shake").motion.shakes
    assert shakes.count == 1
    assert shakes.duration_s == pytest.approx(1.0, abs=0.4)
    expected = 30 * 2 * math.pi * 6 / 30 / 1280
    assert shakes.amplitude == pytest.approx(expected, abs=0.005)
    assert analyzed("shake").motion.punches.count == 0


def test_rgb_splits_and_an_odd_frame_are_glitches(
    analyzed: Callable[[str], ReferenceVideoFeatures],
) -> None:
    glitches = analyzed("glitch").glitches
    (split,) = glitches.splits
    first, last = sv.SPLIT_FRAMES
    assert split.start == pytest.approx(first * FRAME, abs=FRAME)
    assert split.end == pytest.approx((last + 1) * FRAME, abs=FRAME)
    (spike,) = glitches.spikes
    assert spike.start == pytest.approx(sv.SPIKE_FRAME * FRAME, abs=FRAME)
    assert spike.end - spike.start == pytest.approx(FRAME, abs=0.001)
    assert glitches.per_minute == pytest.approx(2 / 0.1)


@pytest.mark.parametrize("name", ["flashes", "cuts"])
def test_flashes_and_cuts_are_no_glitches(
    analyzed: Callable[[str], ReferenceVideoFeatures], name: str
) -> None:
    features = analyzed(name)
    assert features.glitches.spikes == [] and features.glitches.splits == []
    assert features.video.flashes.flashes or features.video.cuts.cuts


@pytest.mark.parametrize(
    ("angle", "strength"),
    [(None, 0.0), ("PI/8", 0.25), ("PI/5", 0.4), ("PI/4", 0.5)],
)
def test_the_vignette_strength_is_the_lens_angle_over_a_right_angle(
    tmp_path: Path, angle: str | None, strength: float
) -> None:
    look = analyze_video(sv.make_look(tmp_path / "look.mp4", angle)).look
    assert look.vignette == pytest.approx(strength, abs=0.03)
    assert look.grain == 0


@pytest.mark.parametrize("noise", [20, 30])
def test_the_grain_is_the_sigma_of_the_luma_noise(tmp_path: Path, noise: int) -> None:
    look = analyze_video(sv.make_look(tmp_path / "grain.mp4", "PI/5", noise)).look
    # ffmpeg's noise filter adds Gaussian noise of sigma strength / sqrt(3)
    # to the limited-range luma; full range stretches it by 255 / 219.
    sigma = noise / math.sqrt(3) / 219
    assert look.grain == pytest.approx(sigma, rel=0.15)
    assert look.vignette == pytest.approx(0.4, abs=0.03)


def test_the_stored_features_are_json_numbers(
    made: Callable[[str], Path], yamnet_cfg: Settings
) -> None:
    stored = measure_features(made("beat_cuts"), yamnet_cfg)
    assert set(stored) == {
        "video",
        "rhythm",
        "motion",
        "look",
        "glitches",
        "captions",
        "audio",
        "structure",
    }
    assert stored["rhythm"]["cuts_on_beat"] == pytest.approx(0.8)
    assert stored["audio"]["loudness_curve"]
    assert all(isinstance(level, float) for level in stored["audio"]["loudness_curve"])
    assert stored["structure"]["first_effect"] == "flash"
    first = stored["structure"]["time_to_first_effect"]
    assert first == pytest.approx(sv.BEAT_FLASH_FRAME * FRAME, abs=FRAME)
    assert stored["video"]["fps"] == fx.FPS
    assert stored["motion"]["punches"] == {
        "count": 0,
        "per_minute": 0.0,
        "amplitude": None,
        "duration_s": None,
    }
