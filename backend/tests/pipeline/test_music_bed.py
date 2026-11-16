"""Pipeline tests of the Pro Edit music and audio effects (SPEC-v3 3.3,
TASK-215): rendered with ffmpeg on a silent 6 s source, a music bed dips
under speech by its duck_db, a silence before a drop is silent and the
drop is a spike on its frame, the music runs on across the silence, and
each audio effect changes its window only."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import EdlItem
from clipforge.proedit.audio.drop import drop_moves
from clipforge.proedit.snap import PlanTiming
from edl_fakes import item, plan
from proedit_sound import (
    FPS,
    RATE,
    Samples,
    level_db,
    levels_db,
    onset_frame,
    render_sound,
    silent_video,
)

DURATION = 4.0


@pytest.fixture(scope="module")
def silent(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return silent_video(tmp_path_factory.mktemp("music") / "silent.mp4")


def loop(directory: Path, name: str, source: str) -> Path:
    """Write the lavfi audio source as a 44.1 kHz stereo FLAC loop."""
    path = directory / f"{name}.flac"
    run_ffmpeg(["-f", "lavfi", "-i", source, "-ac", "2", "-c:a", "flac", path])
    return path


@pytest.fixture(scope="module")
def library(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Music loops as library sounds (tonal: AAC keeps their waveform, not
    a noise's): "1" a steady two-tone chord (2 s, whole cycles), "2" a chirp
    rising from 200 to 800 Hz (3 s: every moment differs), "3" a 60 Hz bass
    tone (2 s), "4" a bright chord: a quiet 100 Hz under 8 and 12 kHz."""
    directory = tmp_path_factory.mktemp("loops")
    chord = "aevalsrc='0.25*sin(2*PI*220*t)+0.25*sin(2*PI*330*t)':s=44100:d=2"
    chirp = "aevalsrc='0.3*sin(2*PI*(200*t+100*t*t))':s=44100:d=3"
    bright = (
        "aevalsrc='0.05*sin(2*PI*100*t)+0.3*sin(2*PI*8000*t)"
        "+0.3*sin(2*PI*12000*t)':s=44100:d=2"
    )
    return {
        "1": loop(directory, "chord", chord),
        "2": loop(directory, "chirp", chirp),
        "3": loop(directory, "bass", "sine=frequency=60:sample_rate=44100:d=2"),
        "4": loop(directory, "bright", bright),
    }


def bed(id: int, start: float, end: float, asset: str, **params: object) -> EdlItem:
    return item(id, "music_bed", start, end, params={"asset": asset, **params})


def effect(id: int, start: float, end: float, name: str, amount: float) -> EdlItem:
    return item(id, "audio_fx", start, end, params={"effect": name, "amount": amount})


@pytest.mark.parametrize(
    ("duck_db", "duck"), [(12.0, True), (6.0, True), (12.0, False)]
)
def test_the_music_dips_under_speech_by_its_duck_db(
    silent: Path,
    library: dict[str, Path],
    tmp_path: Path,
    duck_db: float,
    duck: bool,
) -> None:
    items = [bed(1, 0.0, DURATION, "1", gain_db=-6, duck=duck, duck_db=duck_db)]
    sound = render_sound(tmp_path, silent, items, library, speech=((1.5, 2.5),))
    alone = level_db(sound, 0.5, 1.3)
    spoken = level_db(sound, 1.7, 2.3)
    after = level_db(sound, 2.8, 3.6)
    assert alone == pytest.approx(-18.0, abs=1.0)  # a -12 dBFS chord at -6 dB
    assert alone - spoken == pytest.approx(duck_db if duck else 0.0, abs=1.0)
    assert after == pytest.approx(alone, abs=0.5)


def test_the_silence_before_a_drop_is_silent_and_the_drop_spikes_on_its_frame(
    silent: Path, library: dict[str, Path], tmp_path: Path
) -> None:
    timing = PlanTiming(FPS, DURATION)
    moves = drop_moves(plan([bed(1, 0.0, DURATION, "1")], "pro"), 3.0, timing)
    kinds = [
        (i.kind, round(i.t_start * FPS), round(i.t_end * FPS)) for i in moves.plan.items
    ]
    assert moves.notes == []
    assert kinds == [
        ("music_bed", 0, 84),
        ("sfx", 36, 84),
        ("silence_before_drop", 84, 90),
        ("music_bed", 90, 120),
        ("sfx", 90, 120),
        ("audio_fx", 90, 108),
    ]
    sound = render_sound(tmp_path, silent, moves.plan.items, library)
    frames = levels_db(sound, RATE // FPS)
    assert frames[85:89].max() < -60  # the silence (its edge frames fade)
    assert frames[80:84].min() > -30  # music and riser up to it
    assert abs(onset_frame(sound, 84, 100) - 90) <= 1
    assert frames[90:93].mean() > frames[78:84].mean() + 3


def test_the_music_runs_on_across_a_silence(
    silent: Path, library: dict[str, Path], tmp_path: Path
) -> None:
    whole = render_sound(tmp_path, silent, [bed(1, 0.0, DURATION, "2")], library)
    items = [
        bed(1, 0.0, 2.8, "2"),
        item(2, "silence_before_drop", 2.8, 3.0),
        bed(3, 3.0, DURATION, "2"),
    ]
    cut = render_sound(tmp_path, silent, items, library, name="cut")
    assert level_db(cut, 2.81, 2.99) < -60
    for start, end in ((0.5, 2.7), (3.1, 3.9)):
        a = whole[round(start * RATE) : round(end * RATE)]
        b = cut[round(start * RATE) : round(end * RATE)]
        assert np.corrcoef(a, b)[0, 1] > 0.98, (start, end)


def window_change(
    tmp_path: Path, silent: Path, library: dict[str, Path], asset: str, fx: EdlItem
) -> tuple[Samples, Samples]:
    """The sound of a bed of asset over the whole clip without and with fx."""
    music = bed(1, 0.0, DURATION, asset, gain_db=-6)
    dry = render_sound(tmp_path, silent, [music], library, name="dry")
    wet = render_sound(tmp_path, silent, [music, fx], library, name="wet")
    return dry, wet


def assert_untouched(
    dry: Samples, wet: Samples, spans: list[tuple[float, float]]
) -> None:
    for start, end in spans:
        a = dry[round(start * RATE) : round(end * RATE)]
        b = wet[round(start * RATE) : round(end * RATE)]
        assert np.corrcoef(a, b)[0, 1] > 0.99, (start, end)
        assert level_db(wet, start, end) == pytest.approx(
            level_db(dry, start, end), abs=0.3
        )


def test_a_bass_boost_raises_the_lows_in_its_window(
    silent: Path, library: dict[str, Path], tmp_path: Path
) -> None:
    fx = effect(2, 1.0, 2.0, "bass_boost", 0.5)
    dry, wet = window_change(tmp_path, silent, library, "3", fx)
    boost = level_db(wet, 1.1, 1.9) - level_db(dry, 1.1, 1.9)
    assert 3.0 < boost < 7.0  # a 6 dB shelf at 100 Hz, measured at 60 Hz
    assert_untouched(dry, wet, [(0.2, 0.95), (2.05, 3.8)])


def test_a_lowpass_sweep_opens_over_its_window(
    silent: Path, library: dict[str, Path], tmp_path: Path
) -> None:
    fx = effect(2, 1.0, 3.0, "lowpass_sweep", 1.0)
    dry, wet = window_change(tmp_path, silent, library, "4", fx)
    muffled = level_db(wet, 1.05, 1.25) - level_db(dry, 1.05, 1.25)
    opened = level_db(wet, 2.75, 2.95) - level_db(dry, 2.75, 2.95)
    assert muffled < -10
    assert opened > -1.5
    assert_untouched(dry, wet, [(0.2, 0.95), (3.05, 3.8)])


def test_a_stutter_repeats_the_first_slice_of_its_window(
    silent: Path, library: dict[str, Path], tmp_path: Path
) -> None:
    # amount 0.5: 2 + 3 = 5 repeats of a 0.2 s slice of the chirp.
    fx = effect(2, 1.0, 2.0, "stutter", 0.5)
    dry, wet = window_change(tmp_path, silent, library, "2", fx)
    first = wet[round(1.01 * RATE) : round(1.19 * RATE)]
    for n in range(1, 5):
        start = 1.0 + n * 0.2
        repeat = wet[round((start + 0.01) * RATE) : round((start + 0.19) * RATE)]
        assert np.corrcoef(first, repeat)[0, 1] > 0.95, n
    original = dry[round(1.21 * RATE) : round(1.39 * RATE)]
    assert abs(np.corrcoef(first, original)[0, 1]) < 0.2
    assert_untouched(dry, wet, [(0.2, 0.95), (2.05, 3.8)])


def test_a_reverb_tail_rings_on_past_its_window(
    silent: Path, library: dict[str, Path], tmp_path: Path
) -> None:
    music = bed(1, 0.5, 1.5, "1", gain_db=-6)
    fx = effect(2, 1.0, 1.5, "reverb_tail", 1.0)
    dry = render_sound(tmp_path, silent, [music], library, name="dry")
    wet = render_sound(tmp_path, silent, [music, fx], library, name="wet")
    assert level_db(dry, 1.55, 1.75) < -70
    assert level_db(wet, 1.55, 1.75) > -35
    assert level_db(wet, 2.2, 3.0) < -70
    assert_untouched(dry, wet, [(0.55, 0.95)])
