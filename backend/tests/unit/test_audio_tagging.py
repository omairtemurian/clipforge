"""Tests of the audio auto-tagging of Pro Edit (SPEC-v3 5.4, TASK-218) on
generated sounds: a click track (tempo), a whoosh sweep, an impact, a riser, a
click, chord progressions (key), steady tones (loudness, energy curve) and
silence."""

from pathlib import Path

import numpy as np
import pytest
from audio_synth import (
    A_MINOR,
    C_MAJOR,
    RATE,
    Wave,
    chords,
    click_track,
    impact,
    riser,
    tone,
    whoosh,
    write_wav,
)
from clipforge.assets import add_asset, get_asset
from clipforge.pipeline.step import StepError
from clipforge.proedit.audio.tagging import (
    CATEGORIES,
    MOODS,
    AudioKind,
    AudioTags,
    analyze_audio,
    energy_curve,
    onset_sharpness,
    tag_asset,
)
from sqlalchemy import Engine
from sqlmodel import Session


def analyzed(
    tmp_path: Path, name: str, samples: Wave, kind: AudioKind = "sfx"
) -> AudioTags:
    """Return the tags of samples written as tmp_path/<name>.wav."""
    return analyze_audio(write_wav(tmp_path / f"{name}.wav", samples), kind)


@pytest.mark.parametrize("bpm", [90, 120, 140])
def test_the_tempo_of_a_click_track_is_found(tmp_path: Path, bpm: int) -> None:
    tags = analyzed(tmp_path, "clicks", click_track(bpm, 12), "music")

    assert tags.bpm == pytest.approx(bpm, abs=2)
    assert tags.category == "music"
    assert tags.duration_s == pytest.approx(12, abs=0.05)


def test_a_sound_effect_has_no_tempo(tmp_path: Path) -> None:
    assert analyzed(tmp_path, "clicks", click_track(120, 12), "sfx").bpm is None


def test_a_long_audio_file_is_music_a_short_one_is_not(tmp_path: Path) -> None:
    long = analyzed(tmp_path, "long", click_track(120, 12), "audio")
    short = analyzed(tmp_path, "short", whoosh(), "audio")

    assert (long.category, long.bpm is not None) == ("music", True)
    assert (short.category, short.bpm) == ("whoosh", None)


def test_a_whoosh_sweep_is_a_soft_whoosh(tmp_path: Path) -> None:
    tags = analyzed(tmp_path, "whoosh", whoosh())

    assert tags.category == "whoosh"
    assert tags.onset_sharpness < 0.6
    assert not tags.sharp


def test_an_impact_is_sharp_and_falls(tmp_path: Path) -> None:
    tags = analyzed(tmp_path, "impact", impact())

    assert tags.category == "impact"
    assert tags.onset_sharpness == 1.0
    assert tags.energy_curve[0] > 10 * tags.energy_curve[1]


def test_a_riser_peaks_late(tmp_path: Path) -> None:
    tags = analyzed(tmp_path, "riser", riser())

    assert tags.category == "riser"
    assert tags.energy_curve == [pytest.approx(0.2, abs=0.1), 1.0]


def test_a_short_sharp_sound_is_a_click(tmp_path: Path) -> None:
    burst = click_track(120, 1)[: int(0.04 * RATE)]

    tags = analyzed(tmp_path, "click", burst)

    assert tags.category == "click"
    assert tags.onset_sharpness == 1.0
    assert tags.loudness_lufs is None


@pytest.mark.parametrize(
    ("progression", "key"), [(C_MAJOR, "C major"), (A_MINOR, "A minor")]
)
def test_the_key_of_music_is_found(
    tmp_path: Path, progression: list[tuple[int, ...]], key: str
) -> None:
    assert analyzed(tmp_path, "chords", chords(progression, 3), "music").key == key


def test_a_sound_effect_has_no_key(tmp_path: Path) -> None:
    assert analyzed(tmp_path, "chords", chords(C_MAJOR, 3), "sfx").key is None


def test_the_loudness_is_read_in_lufs(tmp_path: Path) -> None:
    quiet = analyzed(tmp_path, "quiet", tone(1000, 3, 0.05))
    loud = analyzed(tmp_path, "loud", tone(1000, 3, 0.5))

    assert quiet.loudness_lufs == pytest.approx(-29, abs=1)
    assert loud.loudness_lufs == pytest.approx(-9, abs=1)


def test_the_energy_curve_has_one_value_per_second(tmp_path: Path) -> None:
    steps = np.concatenate(
        [tone(440, 1, 0.05), tone(440, 1, 0.25), tone(440, 1.5, 0.5)]
    )

    tags = analyzed(tmp_path, "steps", steps)

    assert tags.energy_curve == [
        pytest.approx(0.1, abs=0.02),
        pytest.approx(0.5, abs=0.05),
        pytest.approx(1.0, abs=0.02),
        pytest.approx(1.0, abs=0.02),
    ]
    assert max(tags.energy_curve) == 1.0


def test_silence_is_other_calm_and_unmeasured(tmp_path: Path) -> None:
    tags = analyzed(tmp_path, "silence", np.zeros(2 * RATE))

    assert (tags.category, tags.mood) == ("other", "calm")
    assert tags.loudness_lufs is None
    assert tags.energy_curve == [0.0, 0.0]
    assert tags.onset_sharpness == 0.0


def test_category_and_mood_are_known_names(tmp_path: Path) -> None:
    for name, samples in (("a", whoosh()), ("b", impact()), ("c", riser())):
        tags = analyzed(tmp_path, name, samples)
        assert tags.category in CATEGORIES
        assert tags.mood in MOODS


def test_a_loud_dense_sound_is_more_intense_than_a_quiet_low_one(
    tmp_path: Path,
) -> None:
    low = analyzed(tmp_path, "low", tone(100, 3, 0.03))
    bright = analyzed(tmp_path, "bright", riser())

    assert low.mood == "calm"
    assert bright.mood == "intense"


def test_onset_sharpness_and_energy_curve_edge_cases() -> None:
    assert onset_sharpness(np.array([-30.0, -20.0])) == 0.0
    assert energy_curve(np.zeros(0, np.float32)) == [0.0]
    assert energy_curve(np.full(RATE + 10, 0.2, np.float32)) == [1.0, 1.0]


def test_a_file_that_is_not_audio_cannot_be_analyzed(tmp_path: Path) -> None:
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not audio at all")

    with pytest.raises(StepError, match="cannot read the music"):
        analyze_audio(broken)


def test_tag_asset_stores_the_analysis_on_the_asset(
    engine: Engine, tmp_path: Path
) -> None:
    path = write_wav(tmp_path / "whoosh.wav", whoosh())
    with Session(engine) as session:
        asset = add_asset(session, "sfx", str(path), "CC0 1.0", tags=["mine"])

        tagged = tag_asset(session, asset)
        stored = get_asset(session, asset.id)

    assert stored == tagged
    assert tagged.category == "whoosh"
    assert tagged.mood in MOODS
    assert tagged.loudness_lufs is not None
    assert tagged.energy_curve == [1.0]
    assert tagged.bpm is None
    assert tagged.tags == ["mine", "whoosh", tagged.mood, "soft-attack"]


def test_a_given_category_wins_over_the_found_one(
    engine: Engine, tmp_path: Path
) -> None:
    path = write_wav(tmp_path / "whoosh.wav", whoosh())
    with Session(engine) as session:
        asset = add_asset(session, "sfx", str(path), "CC0 1.0")

        tagged = tag_asset(session, asset, category="swoosh")

    assert tagged.category == "swoosh"
    assert "swoosh" in tagged.tags


def test_tag_asset_leaves_an_unreadable_asset_unchanged(
    engine: Engine, tmp_path: Path
) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"nope")
    with Session(engine) as session:
        asset = add_asset(session, "sfx", str(path), "CC0 1.0")

        with pytest.raises(StepError):
            tag_asset(session, asset)

        assert get_asset(session, asset.id) == asset
