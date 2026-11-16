"""Tests of AI voiceover (SPEC-v2 3.5, pipeline/voiceover): the spoken files
and their cache, the voiceover items, and the clip's own sound ducked under
them, measured with astats on renders of the fixture's speech (0.5-2.89 s
and 3.46-6.05 s). The voiceover in the renders is muted (volume 0), so the
mix is the clip's sound alone."""

import math
import re
from pathlib import Path

import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import FaceBox, Timeline, TrackItem, VoiceoverProps
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.timeline_graph import Layer, mix_graph
from clipforge.pipeline.voiceover import (
    DUCK_GAIN,
    duck_filter,
    duck_windows,
    fit_problem,
    next_item_id,
    speak,
    spoken_path,
    voiceover_dir,
    voiceover_item,
)
from tts_fakes import PIPER_VOICE, SECONDS_PER_CHAR, piper_runs, piper_settings

LENGTH = 7.0
WINDOW = (3.7, 5.9)
INSIDE = (4.0, 1.5)
OUTSIDE = (1.0, 1.5)
SIZE = (180, 320)


def rms_db(path: Path, start: float, length: float) -> float:
    """Return the RMS level in dBFS of path's sound from start for length
    seconds, as astats measures it."""
    stderr = run_ffmpeg(
        ["-ss", f"{start}", "-t", f"{length}", "-i", path, "-map", "0:a:0"]
        + ["-af", "astats=measure_perchannel=none:measure_overall=RMS_level"]
        + ["-f", "null", "-"],
        loglevel="info",
    ).stderr.decode()
    return float(re.findall(r"RMS level dB: (\S+)", stderr)[-1])


@pytest.fixture(scope="module")
def speech(tmp_path_factory: pytest.TempPathFactory, sample_mp4: Path) -> Path:
    """The fixture's first LENGTH seconds as a 320x240 h264/aac video."""
    path = tmp_path_factory.mktemp("speech") / "speech.mp4"
    run_ffmpeg(
        ["-t", f"{LENGTH}", "-i", sample_mp4, "-s", "320x240", "-c:v", "libx264"]
        + ["-pix_fmt", "yuv420p", "-c:a", "aac", path]
    )
    return path


@pytest.fixture(scope="module")
def tone(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 3 s sine, the voiceover's file."""
    path = tmp_path_factory.mktemp("tone") / "voice.wav"
    run_ffmpeg(["-f", "lavfi", "-i", "sine=f=300:r=24000:d=3", path])
    return path


def render(source: Path, layers: list[Layer], output: Path) -> Path:
    """Render 0-LENGTH s of source at SIZE with layers."""
    faces: list[list[FaceBox]] = [[] for _ in sample_times(0.0, LENGTH)]
    plan = plan_crop(ClipSpan(7, 0.0, LENGTH), "9:16", (320, 240), faces, [])
    return render_clip(
        source,
        output,
        0.0,
        LENGTH,
        plan,
        "fill",
        RenderSettings(),
        size=SIZE,
        layers=layers,
    )


def muted(tone: Path, duck: bool) -> Layer:
    """A muted voiceover layer over WINDOW that ducks if duck."""
    item = TrackItem(id="v", kind="audio", asset_id=1, start=WINDOW[0], end=WINDOW[1])
    return Layer("voiceover", item, VoiceoverProps(volume=0, duck=duck), tone)


def test_the_clip_sound_is_ducked_under_a_voiceover_only(
    speech: Path, tone: Path, tmp_path: Path
) -> None:
    ducked = render(speech, [muted(tone, True)], tmp_path / "ducked.mp4")
    plain = render(speech, [muted(tone, False)], tmp_path / "plain.mp4")

    drop = rms_db(plain, *INSIDE) - rms_db(ducked, *INSIDE)
    assert drop == pytest.approx(-20 * math.log10(DUCK_GAIN), abs=1.5)
    assert rms_db(ducked, *OUTSIDE) == pytest.approx(rms_db(plain, *OUTSIDE), abs=0.5)
    assert rms_db(plain, *INSIDE) > -40


def test_the_voiceover_is_heard_in_the_mix(
    speech: Path, tone: Path, tmp_path: Path
) -> None:
    item = TrackItem(id="v", kind="audio", asset_id=1, start=WINDOW[0], end=WINDOW[1])
    layer = Layer("voiceover", item, VoiceoverProps(volume=1, duck=True), tone)
    mixed = render(speech, [layer], tmp_path / "mixed.mp4")
    silent = render(speech, [muted(tone, True)], tmp_path / "silent.mp4")

    assert rms_db(mixed, *INSIDE) > rms_db(silent, *INSIDE) + 6


def test_the_duck_filter_ramps_around_each_window() -> None:
    assert duck_filter([]) == ""
    assert duck_filter([(1.0, 2.0)]) == (
        "volume=volume='1-0.75*min(clip((t-0.850)/0.15,0,1),"
        "clip((2.150-t)/0.15,0,1))':eval=frame"
    )
    assert duck_filter([(1.0, 2.0), (3.0, 4.0)]).count("max(") == 1


def test_only_voiceovers_that_duck_lower_the_clip_sound(tone: Path) -> None:
    a = TrackItem(id="a", kind="audio", asset_id=1, start=4.0, end=5.0)
    b = TrackItem(id="b", kind="audio", asset_id=1, start=1.0, end=2.0)
    c = TrackItem(id="c", kind="audio", asset_id=1, start=6.0, end=7.0)
    pairs = [
        (a, VoiceoverProps()),
        (b, VoiceoverProps()),
        (c, VoiceoverProps(duck=False)),
    ]

    assert duck_windows(pairs) == [(1.0, 2.0), (4.0, 5.0)]
    graph = mix_graph(
        [Layer("voiceover", item, props, tone) for item, props in pairs], "[0:a]", "[a]"
    )
    assert graph.startswith(f"[0:a]{duck_filter([(1.0, 2.0), (4.0, 5.0)])}[ducked];")
    assert "[ducked][mix0][mix1][mix2]amix=inputs=4" in graph
    plain = mix_graph(
        [Layer("voiceover", c, VoiceoverProps(duck=False), tone)], "[0:a]", "[a]"
    )
    assert "volume='" not in plain


def test_speak_writes_each_line_once(tmp_path: Path) -> None:
    cfg = piper_settings(tmp_path, data_dir=tmp_path / "data")
    voice = f"piper:{PIPER_VOICE}"

    first = speak("Hello there.", voice, 1.0, cfg)
    again = speak("Hello there.", voice, 1.0, cfg)
    faster = speak("Hello there.", voice, 1.25, cfg)

    assert first == again and first.path == spoken_path("Hello there.", voice, 1.0, cfg)
    assert first.path.parent == voiceover_dir(cfg) == tmp_path / "data" / "voiceover"
    assert first.seconds == pytest.approx(12 * SECONDS_PER_CHAR, abs=0.001)
    assert faster.path != first.path and faster.seconds < first.seconds
    assert len(piper_runs(Path(cfg.piper_bin))) == 2
    assert sorted(p.name for p in voiceover_dir(cfg).iterdir()) == sorted(
        [first.path.name, faster.path.name]
    )


def test_a_failed_speak_leaves_no_file(tmp_path: Path) -> None:
    cfg = piper_settings(tmp_path, data_dir=tmp_path / "data")
    with pytest.raises(Exception, match="piper exited"):
        speak("FAIL", f"piper:{PIPER_VOICE}", 1.0, cfg)
    assert list(voiceover_dir(cfg).iterdir()) == []


def test_items_get_free_ids_and_must_fit_the_clip() -> None:
    taken = TrackItem(id="voiceover-1", kind="audio", asset_id=1, start=0, end=1)
    other = TrackItem(id="voiceover-2", kind="audio", asset_id=1, start=0, end=1)
    tracks = Timeline(voiceover=[taken], sfx=[other])
    item = voiceover_item(
        "voiceover-3", 9, 1.23456, 2.5, VoiceoverProps(text="Hi", voice="piper:x")
    )

    assert next_item_id(tracks) == "voiceover-3"
    assert next_item_id(Timeline()) == "voiceover-1"
    assert (item.start, item.end, item.asset_id) == (1.235, 3.735, 9)
    assert item.props["text"] == "Hi" and item.props["duck"] is True
    assert fit_problem(5.0, 5.0, 10.0) is None
    problem = fit_problem(8.0, 3.0, 10.0)
    assert problem is not None and "lasts 3.00 s" in problem and "2.00 s" in problem
