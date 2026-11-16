"""Caption, audio and structure features of style references (TASK-230,
SPEC-v3 4.3) on generated references with known captions
(style_caption_fixtures), music, SFX and speech (style_audio_fixtures) and
cuts and endings (feature_fixtures, style_caption_fixtures).

Tolerances (docs/decisions.md): caption size ±10 % of the font's cap
height, position ±0.01 of the frame, color ±12 per channel; BPM ±1; drops
±1 video frame; SFX onsets ±0.03 s (librosa's 256-sample hop is 0.012 s);
loudness ±0.5 dB of the RMS level of a sine; speech share ≥0.4 for
speech that fills half the clip.
"""

from collections.abc import Callable
from pathlib import Path

import feature_fixtures as fx
import numpy as np
import pytest
import style_audio_fixtures as af
import style_caption_fixtures as cf
from clipforge.pipeline.loudness import CENTER_S, HOP_S, Envelope
from clipforge.pipeline.yamnet import Yamnet
from clipforge.proedit.features.ocr import parse_tsv, tesseract_path
from clipforge.proedit.style import analyze_captions as captions_module
from clipforge.proedit.style.analyze_audio import (
    AudioFeatures,
    analyze_audio,
    on_music,
    silence_before,
)
from clipforge.proedit.style.analyze_captions import analyze_captions
from clipforge.proedit.style.analyze_structure import (
    Effect,
    analyze_structure,
    density,
)
from clipforge.proedit.style.analyze_video import analyze_video

needs_tesseract = pytest.mark.skipif(
    tesseract_path() is None, reason="tesseract is not installed"
)
needs_voice = pytest.mark.skipif(not af.has_voice(), reason="no `say` program")
SFX = [3.125, 10.875, 12.375, 14.625]
FRAME = 1 / 30


@pytest.fixture(scope="module")
def folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A folder for the references of this module."""
    return tmp_path_factory.mktemp("style_refs")


@pytest.fixture(scope="module")
def music(folder: Path, yamnet_model: Yamnet) -> Callable[[bool], AudioFeatures]:
    """Return the audio features of the 16 s music bed with SFX, with or
    without a silence before its drop, analyzed once each."""
    cache: dict[bool, AudioFeatures] = {}

    def features(gap: bool) -> AudioFeatures:
        if gap not in cache:
            audio = af.add_sfx(af.bed(16.0, gap=gap), SFX)
            path = af.reference(folder / f"music_{gap}.mp4", audio)
            found = analyze_audio(path, yamnet_model)
            assert found is not None
            cache[gap] = found
        return cache[gap]

    return features


@needs_tesseract
def test_burned_in_captions_give_their_words_size_place_and_color(
    folder: Path,
) -> None:
    found = analyze_captions(cf.make_captions(folder / "captions.mp4"))
    assert found is not None
    assert found.frames == 8
    assert found.text_share == 0.75
    assert found.lines == 6
    assert found.words_per_line == 3
    assert found.size_ratio == pytest.approx(cf.cap_height() / cf.HEIGHT, rel=0.1)
    assert found.position_x == pytest.approx(0.5, abs=0.01)
    assert found.position_y == pytest.approx(cf.line_center_y(), abs=0.01)
    assert found.color is not None
    rgb = [int(found.color[i : i + 2], 16) for i in (1, 3, 5)]
    assert rgb == pytest.approx(list(cf.COLOR), abs=12)
    # Two samples of each caption: (10 + 1 + 5) capitals of (10 + 9 + 5) letters.
    assert found.uppercase_ratio == pytest.approx(16 / 24, abs=1e-4)


@needs_tesseract
def test_a_video_without_captions_has_no_caption_lines(folder: Path) -> None:
    found = analyze_captions(fx.make_cuts(folder / "cuts.mp4"))
    assert found is not None
    assert found.lines == 0
    assert found.text_share == 0
    assert found.words_per_line is None and found.color is None


def test_without_tesseract_there_are_no_caption_features(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(captions_module, "tesseract_path", lambda: None)
    assert analyze_captions(folder / "never-read.mp4") is None


def test_tesseract_tsv_rows_become_words_of_their_image() -> None:
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
    header += "\tleft\ttop\twidth\theight\tconf\ttext"
    rows = [
        "1\t1\t0\t0\t0\t0\t0\t0\t540\t960\t-1\t",
        "5\t1\t1\t1\t1\t1\t76\t672\t120\t41\t96.5\tTHIS",
        "5\t2\t1\t1\t2\t1\t80\t670\t90\t42\t30.0\tWart",
        "5\t3\t2\t1\t1\t2\t10\t20\t30\t40\t91.0\t",
    ]
    ((page, word),) = parse_tsv("\n".join([header, *rows]))
    assert page == 0
    assert word.text == "THIS" and word.line == (1, 1, 1)
    assert (word.left, word.top, word.width, word.height) == (76, 672, 120, 41)


def test_music_gives_tempo_drop_and_the_silence_before_it(
    music: Callable[[bool], AudioFeatures],
) -> None:
    for gap in (True, False):
        found = music(gap)
        assert found.has_music and found.music_share > 0.9
        assert found.speech_share < 0.1
        assert found.bpm == pytest.approx(af.BPM, abs=1)
        assert found.drops == [pytest.approx(af.DROP_S, abs=FRAME)]
        assert found.silence_before_drop == (1 if gap else 0)


def test_sfx_are_the_onsets_off_the_beat(
    music: Callable[[bool], AudioFeatures],
) -> None:
    found = music(True)
    assert found.sfx_onsets == pytest.approx(SFX, abs=0.03)
    assert found.sfx_per_minute == pytest.approx(len(SFX) / (16 / 60), rel=0.01)


def test_the_loudness_curve_follows_the_level(
    folder: Path, yamnet_model: Yamnet
) -> None:
    t = af.times(6.0)
    tone = np.sin(2 * np.pi * 440 * t) * np.where(t < 3.0, 0.5, 0.05)
    found = analyze_audio(af.reference(folder / "tone.mp4", tone), yamnet_model)
    assert found is not None
    curve = found.loudness_curve
    assert found.loudness_step_s == 0.5
    assert len(curve) == 12
    # The RMS of a sine of amplitude a is a / sqrt(2): -9.03 / -29.03 dBFS.
    assert curve[1:5] == pytest.approx([-9.03] * 4, abs=0.5)
    assert curve[7:11] == pytest.approx([-29.03] * 4, abs=0.5)
    assert found.drops == []


@needs_voice
def test_speech_is_no_music_and_its_onsets_are_no_sfx(
    folder: Path, yamnet_model: Yamnet
) -> None:
    words = af.speech(folder, "Wait for it. This is the craziest thing I have seen.")
    spoken = af.place(af.times(10.0) * 0, words, 1.0)
    audio = af.add_sfx(spoken, [0.4, 8.5, 2.0])
    found = analyze_audio(af.reference(folder / "speech.mp4", audio), yamnet_model)
    assert found is not None
    assert found.speech_share >= 0.4
    assert not found.has_music and found.bpm is None and found.drops == []
    assert found.sfx_onsets == pytest.approx([0.4, 8.5], abs=0.03)


def test_a_video_without_audio_has_no_audio_features(
    folder: Path, yamnet_model: Yamnet
) -> None:
    assert analyze_audio(fx.make_cuts(folder / "silent.mp4"), yamnet_model) is None


def test_on_music_means_on_a_beat_or_half_beat_of_the_grid() -> None:
    beats = [1.0, 1.5, 2.0, 2.62, 3.0]  # one beat snapped onto an SFX
    assert on_music(2.5, beats, 120)
    assert on_music(2.75 + 0.06, beats, 120)
    assert not on_music(2.62, beats, 120)
    assert not on_music(2.0, beats, None)


def test_a_silence_must_be_far_under_the_drop_and_long_enough() -> None:
    def envelope(quiet_frames: int) -> Envelope:
        levels = np.full(200, -20.0)
        levels[100 - quiet_frames : 100] = -60.0
        return Envelope(start=2.0 - CENTER_S - 100 * HOP_S, levels=levels)

    assert silence_before(envelope(30), 2.0, 0.5) is True
    assert silence_before(envelope(5), 2.0, 0.5) is False


def test_structure_counts_effects_hook_and_ending(
    folder: Path, music: Callable[[bool], AudioFeatures]
) -> None:
    cuts = fx.make_cuts(folder / "cuts_structure.mp4")
    found = analyze_structure(cuts, analyze_video(cuts), None)
    assert found.time_to_first_effect == pytest.approx(fx.CUTS[0], abs=FRAME)
    assert found.first_effect == "cut"
    assert found.hook_s == pytest.approx(fx.CUTS[0], abs=FRAME)
    assert found.ending == "hard_cut"
    for loop, ending in ((True, "loop"), (False, "hard_cut")):
        path = cf.make_ending(folder / f"ending_{loop}.mp4", loop=loop)
        video = analyze_video(path)
        assert analyze_structure(path, video, None).ending == ending
    path = cf.make_ending(folder / "ending_music.mp4", loop=True, seconds=16.0)
    with_music = analyze_structure(path, analyze_video(path), music(True))
    assert with_music.first_effect == "sfx"
    assert with_music.time_to_first_effect == pytest.approx(SFX[0], abs=0.03)
    assert with_music.hook_s == pytest.approx(af.DROP_S, abs=FRAME)


def test_effect_density_counts_each_five_seconds() -> None:
    effects = [Effect(time=t, kind="cut") for t in (0.5, 1.0, 4.99, 5.0, 11.9)]
    assert density(effects, 12.0) == [3, 1, 1]
    assert density([], 3.0) == [0]
