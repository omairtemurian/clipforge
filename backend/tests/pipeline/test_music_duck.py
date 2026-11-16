"""Tests of the background music (SPEC-v2 3.5, pipeline/music): the bundled
loops and their licenses, the fade and duck filters, and ducking measured
with astats on the fixture's speech (0.5-2.89 s and 3.46-6.05 s; silent
gaps 2.89-3.46 s and 6.05-6.75 s): a bundled loop ducked by the speech
alone, and a whole render whose music is a 6 kHz tone (the speech has
nothing there, so a narrow band-pass hears only the music in the mix)."""

import re
from pathlib import Path

import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import ffprobe_json, run_ffmpeg
from clipforge.models import FaceBox, MusicProps, TrackItem
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.music import (
    BUNDLED_TRACKS,
    MUSIC_DIR,
    MUSIC_LICENSE,
    BundledTrack,
    bundled_track,
    duck_filter,
    music_filters,
)
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.timeline_graph import Layer

LENGTH = 7.0
SPEECH = [(1.0, 1.5), (4.0, 1.5)]
GAPS = [(3.15, 0.3), (6.4, 0.3)]
TONE_HZ = 6000
BAND = f"bandpass=f={TONE_HZ}:width_type=h:w=100"
SIZE = (180, 320)


def rms_db(path: Path, start: float, length: float, band: bool = False) -> float:
    """Return the RMS level in dBFS of path's sound from start for length
    seconds (only around TONE_HZ if band), as astats measures it."""
    filters = [BAND, BAND] if band else []
    filters.append("astats=measure_perchannel=none:measure_overall=RMS_level")
    stderr = run_ffmpeg(
        ["-ss", f"{start}", "-t", f"{length}", "-i", path, "-map", "0:a:0"]
        + ["-af", ",".join(filters), "-f", "null", "-"],
        loglevel="info",
    ).stderr.decode()
    return float(re.findall(r"RMS level dB: (\S+)", stderr)[-1])


def mean_db(
    path: Path, windows: list[tuple[float, float]], band: bool = False
) -> float:
    """Return the mean of rms_db over the windows."""
    return sum(rms_db(path, *window, band=band) for window in windows) / len(windows)


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
    """A 2 s TONE_HZ sine (1/8 full scale, about -21 dBFS RMS): shorter than
    the clip, so the render loops it."""
    path = tmp_path_factory.mktemp("tone") / "tone.flac"
    run_ffmpeg(["-f", "lavfi", "-i", f"sine=f={TONE_HZ}:r=48000:d=2", path])
    return path


def render(source: Path, music: Path, props: MusicProps, output: Path) -> Path:
    """Render 0-LENGTH s of source at SIZE with music on its music track
    over the whole clip."""
    faces: list[list[FaceBox]] = [[] for _ in sample_times(0.0, LENGTH)]
    plan = plan_crop(ClipSpan(7, 0.0, LENGTH), "9:16", (320, 240), faces, [])
    item = TrackItem(id="m", kind="audio", asset_id=1, start=0.0, end=LENGTH)
    return render_clip(
        source,
        output,
        0.0,
        LENGTH,
        plan,
        "fill",
        RenderSettings(),
        size=SIZE,
        layers=[Layer("music", item, props, music)],
    )


def test_every_bundled_track_has_its_file_and_license() -> None:
    licenses = (MUSIC_DIR / "LICENSES.md").read_text()
    files = sorted(path.name for path in MUSIC_DIR.glob("*.flac"))

    assert files == sorted(track.file for track in BUNDLED_TRACKS)
    assert "CC0 1.0" in licenses and MUSIC_LICENSE == "CC0-1.0"
    for track in BUNDLED_TRACKS:
        assert f"`{track.file}` | {track.title} | {', '.join(track.tags)} |" in licenses
        assert track.title in track.attribution and MUSIC_LICENSE in track.attribution
        stream = ffprobe_json(MUSIC_DIR / track.file)["streams"][0]
        assert (stream["codec_name"], stream["sample_rate"]) == ("flac", "48000")
        assert float(stream["duration"]) >= 20
        assert bundled_track(Path("/elsewhere") / track.file) == track
    assert bundled_track("other.flac") is None


def test_music_filters_set_the_volume_and_fade_within_the_item() -> None:
    props = MusicProps(volume=0.4, fade_in=1.5, fade_out=2)

    assert music_filters(props, 10) == (
        "volume=volume=0.4,afade=t=in:st=0:d=1.500,afade=t=out:st=8.000:d=2.000"
    )
    assert music_filters(MusicProps(fade_out=5), 3) == (
        "volume=volume=1,afade=t=out:st=0.000:d=3.000"
    )
    assert music_filters(MusicProps(), 3) == "volume=volume=1"


def test_the_duck_filter_options_exist_in_the_installed_ffmpeg() -> None:
    help_text = run_ffmpeg(["-h", "filter=sidechaincompress"]).stdout.decode()
    options = re.findall(r"(\w+)=", duck_filter().split("=", 1)[1])

    assert duck_filter().startswith("sidechaincompress=")
    for option in options:
        assert re.search(rf"^\s+{option}\s", help_text, re.MULTILINE), option


@pytest.mark.parametrize("track", BUNDLED_TRACKS, ids=lambda track: track.file)
def test_a_bundled_loop_is_lower_during_speech_than_in_the_gaps(
    track: BundledTrack, speech: Path, tmp_path: Path
) -> None:
    out = tmp_path / "ducked.wav"
    filters = music_filters(MusicProps(volume=0.5), LENGTH)
    run_ffmpeg(
        ["-i", speech, "-stream_loop", "-1", "-t", f"{LENGTH}"]
        + ["-i", MUSIC_DIR / track.file, "-filter_complex"]
        + [f"[1:a:0]{filters}[music];[music][0:a:0]{duck_filter()}[ducked]"]
        + ["-map", "[ducked]", out]
    )

    during, between = mean_db(out, SPEECH), mean_db(out, GAPS)

    assert during < between - 6, (during, between)


def test_a_rendered_clips_music_ducks_under_its_speech(
    speech: Path, tone: Path, tmp_path: Path
) -> None:
    rendered = render(speech, tone, MusicProps(), tmp_path / "duck.mp4")

    during = mean_db(rendered, SPEECH, band=True)
    between = mean_db(rendered, GAPS, band=True)

    assert float(ffprobe_json(rendered)["format"]["duration"]) == pytest.approx(
        LENGTH, abs=0.2
    )
    # The 2 s tone loops: it still plays in the last gap, at its level.
    assert between == pytest.approx(-21.0, abs=2.0)
    assert during < between - 6, (during, between)


def test_music_without_duck_stays_at_its_level_under_speech(
    speech: Path, tone: Path, tmp_path: Path
) -> None:
    rendered = render(speech, tone, MusicProps(duck=False), tmp_path / "flat.mp4")

    during = mean_db(rendered, SPEECH, band=True)
    between = mean_db(rendered, GAPS, band=True)

    assert during == pytest.approx(between, abs=1.0)


def test_music_fades_in_from_its_start_and_out_to_its_end(
    speech: Path, tone: Path, tmp_path: Path
) -> None:
    props = MusicProps(volume=0.5, fade_in=2, fade_out=2, duck=False)
    rendered = render(speech, tone, props, tmp_path / "fades.mp4")

    start = rms_db(rendered, 0.0, 0.3, band=True)
    middle = rms_db(rendered, 3.0, 1.0, band=True)
    end = rms_db(rendered, LENGTH - 0.3, 0.25, band=True)

    # Half the volume: about 6 dB under the tone's -21 dBFS.
    assert middle == pytest.approx(-27.0, abs=1.5)
    assert start < middle - 12 and end < middle - 12
