"""Tests of clips rendered without their cut ranges and with their loudness
normalized (SPEC 6.10, 6.11), with ffmpeg: the length and loudness of clip A
of the fixture, pictures and sound still in sync after the cuts, and a silent
clip, whose loudness cannot be measured."""

import logging
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import ffprobe_bin, probe_media, run_ffmpeg
from clipforge.models import Aspect, CropPlan, FaceBox
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from flashes import SAMPLE_RATE, beep_times, flash_times, make_flashes, onsets

MakeMedia = Callable[..., Path]
TARGET_LUFS = -14.0
# Clip A of the fixture, as snap moves it, and its filler cuts (test_polish).
CLIP_A = ClipSpan(1, 0.5, 34.35)
CUTS_A = [(6.2, 7.55), (22.6, 24.15)]
# Clip 1-10 s of the flashes video keeps 0-2, 3.5-3.9 and 4.6-9 s of it on
# frames: the flash at 5 s is cut, those at 2 and 8 s play at 1 and 4.8 s.
FLASH_CLIP = ClipSpan(2, 1.0, 10.0)
FLASH_CUTS = [(3.01, 4.49), (4.9, 5.6)]


def crop_plan(clip: ClipSpan, aspect: Aspect, size: tuple[int, int]) -> CropPlan:
    """Return the crop plan of clip of a source of size, with no faces."""
    faces: list[list[FaceBox]] = [[] for _ in sample_times(clip.start, clip.end)]
    return plan_crop(clip, aspect, size, faces, [])


def integrated_lufs(video: Path) -> float:
    """Return the integrated loudness of video's audio, measured by ebur128."""
    stderr = run_ffmpeg(
        ["-i", video, "-map", "0:a:0", "-af", "ebur128=framelog=quiet"]
        + ["-f", "null", "-"],
        loglevel="info",
    ).stderr.decode()
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", stderr)[-1])


def assert_audio_timed_by_its_samples(video: Path, samples: int) -> None:
    """Assert that the packets of video's audio hold 1024 samples each but
    the last, each from where the one before it ends, up to samples: their
    timestamps place each sample where it was in the source."""
    csv = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-select_streams", "a:0"]
        + ["-show_entries", "packet=pts,duration", "-of", "csv=p=0", str(video)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rows = [line.split(",")[:2] for line in csv.split()]
    packets = [(int(pts), int(duration)) for pts, duration in rows]
    ends = [pts + duration for pts, duration in packets]

    assert {duration for _, duration in packets[:-1]} == {1024}
    assert [pts for pts, _ in packets[1:]] == ends[:-1]
    assert ends[-1] == samples


@pytest.fixture(scope="module")
def clip_a(
    sample_mp4: Path,
    tmp_path_factory: pytest.TempPathFactory,
    render_settings: RenderSettings,
) -> Path:
    """Clip A of the fixture rendered at 9:16 without its filler cuts and
    normalized to TARGET_LUFS."""
    output = tmp_path_factory.mktemp("clip_a") / "1.mp4"
    plan = crop_plan(CLIP_A, "9:16", (1280, 720))
    return render_clip(
        sample_mp4,
        output,
        CLIP_A.start,
        CLIP_A.end,
        plan,
        "fill",
        render_settings,
        cut_ranges=CUTS_A,
        target_lufs=TARGET_LUFS,
    )


@pytest.fixture(scope="module")
def flashes(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 12 s 640x360 30 fps h264/aac video with 48 kHz mono audio, black and
    silent but for the FLASHES."""
    return make_flashes(tmp_path_factory.mktemp("flashes") / "flashes.mp4")


def test_clip_a_lasts_its_length_without_its_cuts(clip_a: Path) -> None:
    length = CLIP_A.end - CLIP_A.start - sum(end - start for start, end in CUTS_A)

    assert probe_media(clip_a).duration == pytest.approx(length, abs=0.2)


def test_clip_a_is_normalized_to_the_target_loudness(
    clip_a: Path, sample_mp4: Path
) -> None:
    info = probe_media(clip_a)

    # The fixture's speech is at -22.8 LUFS: far from the target.
    assert integrated_lufs(sample_mp4) < TARGET_LUFS - 5
    assert integrated_lufs(clip_a) == pytest.approx(TARGET_LUFS, abs=1.5)
    assert (info.audio_codec, info.sample_rate) == ("aac", SAMPLE_RATE)


def test_clip_a_audio_is_timed_by_its_samples(clip_a: Path) -> None:
    # loudnorm normalizes clip A dynamically (its range is over 7 LU), and
    # the timestamps of what it returns of its cut audio are wrong; the
    # render times the samples itself. The parts it keeps last 5.7,
    # 15.0333 and 10.1833 s: 30.9167 s.
    assert_audio_timed_by_its_samples(clip_a, 1_484_000)


@pytest.mark.parametrize("target_lufs", [None, TARGET_LUFS])
def test_cuts_keep_pictures_and_sound_in_sync(
    flashes: Path,
    tmp_path: Path,
    target_lufs: float | None,
    render_settings: RenderSettings,
) -> None:
    output = tmp_path / "2.mp4"
    plan = crop_plan(FLASH_CLIP, "1:1", (640, 360))

    render_clip(
        flashes,
        output,
        FLASH_CLIP.start,
        FLASH_CLIP.end,
        plan,
        "fill",
        render_settings,
        cut_ranges=FLASH_CUTS,
        target_lufs=target_lufs,
    )

    assert probe_media(output).duration == pytest.approx(6.8, abs=0.05)
    assert onsets(flash_times(output)) == pytest.approx([1.0, 4.8], abs=1e-6)
    assert onsets(beep_times(output)) == pytest.approx([1.0, 4.8], abs=0.005)
    assert_audio_timed_by_its_samples(output, round(6.8 * SAMPLE_RATE))


def test_a_silent_clip_is_rendered_without_normalizing(
    make_media: MakeMedia,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    render_settings: RenderSettings,
) -> None:
    source = make_media(
        "silent.mp4",
        *("-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"),
        audio_source=f"anullsrc=channel_layout=mono:sample_rate={SAMPLE_RATE}",
        duration=3.0,
    )
    clip = ClipSpan(3, 0.5, 2.5)
    output = tmp_path / "3.mp4"

    with caplog.at_level(logging.INFO, logger="clipforge.pipeline.render"):
        render_clip(
            source,
            output,
            clip.start,
            clip.end,
            crop_plan(clip, "16:9", (320, 240)),
            "fill",
            render_settings,
            cut_ranges=[(1.0, 1.5)],
            target_lufs=TARGET_LUFS,
        )

    assert probe_media(output).duration == pytest.approx(1.5, abs=0.05)
    assert "audio too quiet to measure" in caplog.text
