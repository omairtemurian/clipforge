"""Pipeline tests of the Pro Edit mix (SPEC-v3 3.3, TASK-216): the dialogue
chain (high-pass, presence, compression, de-ess) measured on tones through
real ffmpeg, and the mastered render: its integrated loudness is -14 +-1 LU
and its true peak at most -1 dBTP, for quiet and loud sources, with and
without music."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import EdlItem
from clipforge.pipeline.loudnorm import measure_filter, measure_loudness
from clipforge.proedit.audio.mix import DIALOGUE_FILTER
from clipforge.proedit.render.run import mastered_filter, render_plan
from edl_fakes import item, plan
from proedit_render import base_of
from proedit_sound import RATE, X264, silent_video

TARGET = -14.0


def tone_gain_db(freq: float, amplitude: float) -> float:
    """The gain in dB that DIALOGUE_FILTER gives a sine of freq Hz at
    amplitude (RMS of the last 2 s of 3, once the compressor settled)."""
    expression = f"aevalsrc={amplitude}*sin(2*PI*{freq}*t):s={RATE}:d=3"
    pcm = run_ffmpeg(
        ["-f", "lavfi", "-i", expression, "-af", DIALOGUE_FILTER]
        + ["-ac", "1", "-f", "f32le", "pipe:1"]
    ).stdout
    samples = np.frombuffer(pcm, np.float32).astype(np.float64)[RATE:]
    return 20 * np.log10(np.sqrt((samples**2).mean()) / (amplitude / np.sqrt(2)))


def test_the_dialogue_chain_cuts_rumble_below_80_hz() -> None:
    assert tone_gain_db(40, 0.02) < tone_gain_db(1000, 0.02) - 10


def test_the_dialogue_chain_boosts_the_presence_around_3_khz() -> None:
    boost = tone_gain_db(3000, 0.02) - tone_gain_db(1000, 0.02)
    assert 1.0 < boost < 4.0


def test_the_dialogue_chain_compresses_loud_speech_more_than_quiet() -> None:
    quiet, loud = tone_gain_db(1000, 0.02), tone_gain_db(1000, 0.5)
    assert quiet - loud > 6


def test_the_dialogue_chain_de_esses_loud_sibilance_only() -> None:
    loud_ess = tone_gain_db(7000, 0.5) - tone_gain_db(1000, 0.5)
    quiet_ess = tone_gain_db(7000, 0.02) - tone_gain_db(1000, 0.02)
    assert loud_ess < -5
    assert abs(quiet_ess) < 1.5


def tone_video(path: Path, amplitude: float) -> Path:
    """A 6 s 1280x720 video whose sound is a 440 Hz tone with a 3 Hz
    tremolo (speech-like swells) of peak amplitude."""
    swell = "(0.6+0.4*sin(2*PI*3*t))"
    sound = f"aevalsrc='{amplitude}*sin(2*PI*440*t)*{swell}':s=48000:d=6"
    run_ffmpeg(
        ["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-f", "lavfi"]
        + ["-i", sound, "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        + ["-c:a", "aac", path]
    )
    return path


def peaky_video(path: Path) -> Path:
    """A 6 s 1280x720 video whose sound is a quiet tone with a loud 2 ms
    click every half second: its true peak is near 0 dBTP, far above what
    a gain to -14 LUFS would leave."""
    sound = (
        "aevalsrc='0.05*sin(2*PI*440*t)"
        "+0.95*lt(mod(t,0.5),0.002)*sin(2*PI*1000*t)':s=48000:d=6"
    )
    run_ffmpeg(
        ["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-f", "lavfi"]
        + ["-i", sound, "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        + ["-c:a", "aac", path]
    )
    return path


def chord_loop(path: Path) -> Path:
    """A 2 s two-tone chord as a 44.1 kHz stereo FLAC loop."""
    chord = "aevalsrc='0.4*sin(2*PI*220*t)+0.4*sin(2*PI*330*t)':s=44100:d=2"
    run_ffmpeg(["-f", "lavfi", "-i", chord, "-ac", "2", "-c:a", "flac", path])
    return path


def measured(media: Path) -> tuple[float, float]:
    """The integrated loudness (LUFS) and true peak (dBTP) of media."""
    loudness = measure_loudness(
        ["-i", media], f"[0:a:0]{measure_filter(TARGET)}[a]", "[a]"
    )
    assert loudness is not None
    return loudness.integrated, loudness.true_peak


def mastered(
    tmp_path: Path, source: Path, items: list[EdlItem], library: dict[str, Path]
) -> Path:
    """The proxy of CLIP of source with items, mastered."""
    base = replace(base_of(source), sounds=library)
    return render_plan(
        base,
        plan(items, "pro"),
        tmp_path / "mastered.mp4",
        quality="proxy",
        settings=X264,
    )


@pytest.mark.parametrize("amplitude", [0.02, 0.2, 0.95])
def test_a_render_is_mastered_to_14_lufs_with_a_true_peak_under_1_dbtp(
    tmp_path: Path, amplitude: float
) -> None:
    source = tone_video(tmp_path / "source.mp4", amplitude)
    output = mastered(tmp_path, source, [], {})
    integrated, peak = measured(output)
    assert integrated == pytest.approx(TARGET, abs=1.0)
    assert peak <= -1.0


def test_a_peaky_source_is_limited_to_a_true_peak_under_1_dbtp(tmp_path: Path) -> None:
    source = peaky_video(tmp_path / "source.mp4")
    assert measured(source)[1] > -1.0
    integrated, peak = measured(mastered(tmp_path, source, [], {}))
    assert integrated == pytest.approx(TARGET, abs=1.0)
    assert peak <= -1.0


def test_a_render_with_a_music_bed_is_mastered_to_14_lufs(tmp_path: Path) -> None:
    source = tone_video(tmp_path / "source.mp4", 0.2)
    bed = item(
        1,
        "music_bed",
        0.5,
        3.5,
        params={"asset": "1", "gain_db": -6.0, "duck_db": 6.0},
    )
    output = mastered(tmp_path, source, [bed], {"1": chord_loop(tmp_path / "1.flac")})
    integrated, peak = measured(output)
    assert integrated == pytest.approx(TARGET, abs=1.0)
    assert peak <= -1.0


def test_a_render_without_master_keeps_the_levels_of_its_source(
    tmp_path: Path,
) -> None:
    source = tone_video(tmp_path / "source.mp4", 0.2)
    kept = render_plan(
        base_of(source),
        plan([], "pro"),
        tmp_path / "kept.mp4",
        quality="proxy",
        settings=X264,
        master=False,
    )
    assert measured(kept)[0] < TARGET - 3


def test_a_silent_sound_is_not_normalized(tmp_path: Path) -> None:
    source = silent_video(tmp_path / "silent.mp4")
    base = base_of(source)
    assert mastered_filter(base, [], 30, ["-i", source]) == ""
    output = mastered(tmp_path, source, [], {})
    assert output.is_file()
