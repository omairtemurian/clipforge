"""Tests of the enhanced speech of rendered clips (SPEC-v2 3.5,
pipeline/enhance): the source is the fixture's first 6 s of speech with white
noise. Rendered with the enhanced voice, the RMS level (astats) of the
pause falls and the speech stays, after the cuts, with loudness
normalization and with a sound layer (its ffmpeg input comes before the
voice's)."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import AudioProps, FaceBox, TrackItem
from clipforge.pipeline.enhance import enhanced_voice
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.timeline_graph import Layer

MakeMedia = Callable[..., Path]
NOISE = "anoisesrc=a=0.03:c=white:r=48000:d=6:seed=1"
CLIP = ClipSpan(7, 0.0, 6.0)
CUTS = [(0.2, 0.6)]
# The fixture speaks 0.5-2.9 s and 3.45-6.05 s; after the cut, in
# rendered-clip seconds, it pauses at 2.5-3.05 s.
NOISE_ONLY = (2.6, 0.35)
SPEECH = (0.7, 1.5)
SIZE = (180, 320)


def rms_db(video: Path, start: float, length: float) -> float:
    """Return the RMS level in dBFS of video's sound from start for length
    seconds, as astats measures it."""
    stderr = run_ffmpeg(
        ["-ss", f"{start}", "-t", f"{length}", "-i", video, "-map", "0:a:0"]
        + ["-af", "astats=measure_perchannel=none:measure_overall=RMS_level"]
        + ["-f", "null", "-"],
        loglevel="info",
    ).stderr.decode()
    return float(re.findall(r"RMS level dB: (\S+)", stderr)[-1])


@pytest.fixture(scope="module")
def noisy(tmp_path_factory: pytest.TempPathFactory, sample_mp4: Path) -> Path:
    """The first 6 s of the fixture as a 320x240 h264/aac video with white
    noise added to its speech."""
    path = tmp_path_factory.mktemp("noisy") / "noisy.mp4"
    run_ffmpeg(
        ["-t", "6", "-i", sample_mp4, "-f", "lavfi", "-i", NOISE]
        + ["-filter_complex", "[0:a][1]amix=inputs=2:normalize=0[a]"]
        + ["-map", "0:v", "-map", "[a]", "-s", "320x240", "-c:v", "libx264"]
        + ["-pix_fmt", "yuv420p", "-c:a", "aac", path]
    )
    return path


def render(
    source: Path,
    output: Path,
    strength: float,
    target_lufs: float | None = None,
    layers: tuple[Layer, ...] = (),
) -> Path:
    """Render CLIP of source with CUTS, its speech enhanced at strength."""
    faces: list[list[FaceBox]] = [[] for _ in sample_times(CLIP.start, CLIP.end)]
    plan = plan_crop(CLIP, "9:16", (320, 240), faces, [])
    with enhanced_voice(source, CLIP.start, CLIP.end, strength) as voice:
        return render_clip(
            source,
            output,
            CLIP.start,
            CLIP.end,
            plan,
            "fill",
            RenderSettings(),
            cut_ranges=CUTS,
            target_lufs=target_lufs,
            size=SIZE,
            layers=layers,
            voice=voice,
        )


def test_the_noise_falls_and_the_speech_stays(noisy: Path, tmp_path: Path) -> None:
    plain = render(noisy, tmp_path / "plain.mp4", 0.0)
    clean = render(noisy, tmp_path / "clean.mp4", 1.0)

    assert rms_db(clean, *NOISE_ONLY) < rms_db(plain, *NOISE_ONLY) - 6
    assert rms_db(clean, *SPEECH) > rms_db(plain, *SPEECH) - 8


def test_zero_strength_renders_the_source_sound(noisy: Path) -> None:
    with enhanced_voice(noisy, 0.0, 4.0, 0.0) as voice:
        assert voice is None


def test_the_voice_file_is_deleted_after_the_render(noisy: Path) -> None:
    with enhanced_voice(noisy, 0.0, 4.0, 0.5) as voice:
        assert voice is not None and voice.is_file()

    assert not voice.exists()


def test_the_enhanced_voice_is_measured_for_loudness(
    noisy: Path, tmp_path: Path
) -> None:
    plain = render(noisy, tmp_path / "plain.mp4", 0.0, -14.0)
    clean = render(noisy, tmp_path / "clean.mp4", 1.0, -14.0)

    assert rms_db(clean, *SPEECH) - rms_db(clean, *NOISE_ONLY) > (
        rms_db(plain, *SPEECH) - rms_db(plain, *NOISE_ONLY) + 6
    )


def test_a_sound_layer_is_mixed_with_the_enhanced_voice(
    noisy: Path, tmp_path: Path, make_media: MakeMedia
) -> None:
    beep = make_media("layer_beep.m4a", "-c:a", "aac", size=None, duration=0.5)
    item = TrackItem(id="sfx-1", kind="audio", asset_id=1, start=2.55, end=2.95)
    layer = Layer("sfx", item, AudioProps(volume=1.0), beep)

    alone = render(noisy, tmp_path / "alone.mp4", 1.0)
    mixed = render(noisy, tmp_path / "mixed.mp4", 1.0, layers=(layer,))

    assert rms_db(mixed, *NOISE_ONLY) > rms_db(alone, *NOISE_ONLY) + 6
    assert rms_db(mixed, *SPEECH) == pytest.approx(rms_db(alone, *SPEECH), abs=1.0)
