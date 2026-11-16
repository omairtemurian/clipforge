"""Tests of the ingest step (SPEC 6.1) with local source files."""

import os
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from clipforge.ffmpeg import extract_frame, ffprobe_json, probe_media, run_ffmpeg
from clipforge.models import ProcessingSettings, SourceMeta
from clipforge.pipeline.ingest import AUDIO, META, SOURCE, THUMB, run
from clipforge.pipeline.step import StepError, StepSettings

MakeMedia = Callable[..., Path]
OUTPUTS = sorted((SOURCE, AUDIO, THUMB, META))
H264_AAC = ("-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac")


class Ingested(NamedTuple):
    """The result of an ingest run: its job directory, return value and progress."""

    job_dir: Path
    meta_path: Path
    progress: list[float]


def ingest(job_dir: Path, source: Path, **timeframe: float) -> Ingested:
    """Run ingest on source with the given timeframe, recording its progress."""
    progress: list[float] = []
    settings = StepSettings(
        source=str(source),
        processing=ProcessingSettings(**timeframe),
        on_progress=progress.append,
    )
    return Ingested(job_dir, run(job_dir, settings), progress)


def read_meta(job_dir: Path) -> SourceMeta:
    """Load the job's meta.json."""
    return SourceMeta.model_validate_json((job_dir / META).read_text())


def is_mp4(path: Path) -> bool:
    """Return True if ffprobe reads path as an MP4-family file."""
    return "mp4" in ffprobe_json(path)["format"]["format_name"].split(",")


def stream_md5(path: Path, stream: str) -> str:
    """Return the MD5 of the packets of the first stream of a type ("v", "a")."""
    args: list[str | Path] = ["-i", path, "-map", f"0:{stream}:0", "-c", "copy"]
    return run_ffmpeg([*args, "-f", "streamhash", "-hash", "md5", "-"]).stdout.decode()


@pytest.fixture(scope="module")
def sample_job(sample_mp4: Path, tmp_path_factory: pytest.TempPathFactory) -> Ingested:
    """sample.mp4 ingested into a fresh job directory."""
    return ingest(tmp_path_factory.mktemp("sample") / "job", sample_mp4)


def test_local_mp4_is_copied_and_every_output_is_written(
    sample_job: Ingested, sample_mp4: Path
) -> None:
    assert sample_job.meta_path == sample_job.job_dir / META
    assert sorted(path.name for path in sample_job.job_dir.iterdir()) == OUTPUTS
    assert (sample_job.job_dir / SOURCE).read_bytes() == sample_mp4.read_bytes()


def test_audio_wav_is_16khz_mono_16bit_pcm(
    sample_job: Ingested, expected: dict[str, Any]
) -> None:
    audio = sample_job.job_dir / AUDIO
    with wave.open(str(audio), "rb") as wav:
        params = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
        seconds = wav.getnframes() / wav.getframerate()
    assert params == (1, 2, 16_000)
    assert seconds == pytest.approx(expected["media"]["duration"], abs=0.05)
    (stream,) = ffprobe_json(audio)["streams"]
    assert stream["codec_name"] == "pcm_s16le"


def test_meta_json_describes_the_source_and_the_whole_timeframe(
    sample_job: Ingested, sample_mp4: Path, expected: dict[str, Any]
) -> None:
    media = expected["media"]
    duration = probe_media(sample_mp4).duration
    assert read_meta(sample_job.job_dir) == SourceMeta(
        title=media["title"],
        duration=duration,
        width=media["width"],
        height=media["height"],
        fps=media["fps"],
        timeframe_start=0.0,
        timeframe_end=duration,
    )


def test_thumbnail_is_the_frame_at_ten_percent_of_the_duration(
    sample_job: Ingested, sample_mp4: Path, tmp_path: Path
) -> None:
    at_10_percent = 0.1 * probe_media(sample_mp4).duration
    frames = {
        offset: extract_frame(
            sample_mp4, tmp_path / f"{offset}.jpg", at_10_percent + offset
        ).read_bytes()
        for offset in (-1.0, 0.0, 1.0)
    }
    thumb = (sample_job.job_dir / THUMB).read_bytes()
    assert thumb == frames[0.0]
    assert thumb not in (frames[-1.0], frames[1.0])


def test_progress_only_rises_and_ends_at_one(sample_job: Ingested) -> None:
    progress = sample_job.progress
    assert len(progress) >= 3
    assert progress == sorted(progress)
    assert 0 < progress[0] and progress[-1] == 1.0


def test_rerun_skips_unless_forced(sample_mp4: Path, tmp_path: Path) -> None:
    first = ingest(tmp_path / "job", sample_mp4)
    outputs = [first.job_dir / name for name in OUTPUTS]
    old = 1_000_000_000.0
    for path in outputs:
        os.utime(path, (old, old))

    again = ingest(first.job_dir, sample_mp4)
    assert again.meta_path == first.meta_path
    assert again.progress == [1.0]
    assert [path.stat().st_mtime for path in outputs] == [old] * len(outputs)

    settings = StepSettings(source=str(sample_mp4))
    assert run(first.job_dir, settings, force=True) == first.meta_path
    assert all(path.stat().st_mtime > old for path in outputs)


def test_mpeg4_mp3_avi_is_transcoded_to_h264_aac_mp4(
    make_media: MakeMedia, tmp_path: Path
) -> None:
    avi = make_media(
        "odd.avi", "-c:v", "mpeg4", "-c:a", "libmp3lame",
        "-metadata", "title=Odd clip", size="321x241",
    )  # fmt: skip
    assert (probe_media(avi).width, probe_media(avi).height) == (321, 241)
    job = ingest(tmp_path / "job", avi)
    source = job.job_dir / SOURCE
    info = probe_media(source)
    assert (info.video_codec, info.pix_fmt, info.audio_codec) == (
        "h264",
        "yuv420p",
        "aac",
    )
    assert is_mp4(source)
    meta = read_meta(job.job_dir)
    assert (meta.title, meta.width, meta.height) == ("Odd clip", 320, 240)
    assert meta.duration == pytest.approx(1.0, abs=0.1)


@pytest.mark.parametrize(
    ("audio_codec", "audio_copied"), [("aac", True), ("libmp3lame", False)]
)
def test_h264_in_matroska_keeps_its_video_and_only_non_aac_audio_is_encoded(
    make_media: MakeMedia, tmp_path: Path, audio_codec: str, audio_copied: bool
) -> None:
    mkv = make_media(
        f"h264-{audio_codec}.mkv", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", audio_codec,
    )  # fmt: skip
    source = ingest(tmp_path / "job", mkv).job_dir / SOURCE
    info = probe_media(source)
    assert (info.video_codec, info.audio_codec) == ("h264", "aac")
    assert is_mp4(source) and not is_mp4(mkv)
    assert stream_md5(source, "v") == stream_md5(mkv, "v")
    assert (stream_md5(source, "a") == stream_md5(mkv, "a")) is audio_copied


def test_h264_that_browsers_cannot_play_is_reencoded_to_yuv420p(
    make_media: MakeMedia, tmp_path: Path
) -> None:
    mp4 = make_media(
        "h264-444.mp4", "-c:v", "libx264", "-pix_fmt", "yuv444p", "-c:a", "aac"
    )
    source = ingest(tmp_path / "job", mp4).job_dir / SOURCE
    info = probe_media(source)
    assert (info.video_codec, info.pix_fmt) == ("h264", "yuv420p")
    assert stream_md5(source, "a") == stream_md5(mp4, "a")


@pytest.mark.parametrize(
    ("timeframe", "start", "end"),
    [
        ({}, 0.0, None),
        ({"timeframe_start": 0.5, "timeframe_end": 1.5}, 0.5, 1.5),
        ({"timeframe_start": 1.0, "timeframe_end": 99.0}, 1.0, None),
    ],
)
def test_timeframe_is_stored_and_ends_by_the_end_of_the_video(
    make_media: MakeMedia,
    tmp_path: Path,
    timeframe: dict[str, float],
    start: float,
    end: float | None,
) -> None:
    """end None stands for the duration of the video."""
    clip = make_media("two-seconds.mp4", *H264_AAC, duration=2.0)
    meta = read_meta(ingest(tmp_path / "job", clip, **timeframe).job_dir)
    assert meta.duration == pytest.approx(2.0, abs=0.05)
    expected_end = meta.duration if end is None else end
    assert (meta.timeframe_start, meta.timeframe_end) == (start, expected_end)


def test_timeframe_that_starts_after_the_video_is_an_error(
    make_media: MakeMedia, tmp_path: Path
) -> None:
    clip = make_media("short.mp4", *H264_AAC)
    with pytest.raises(StepError, match="timeframe starts at 5s"):
        ingest(tmp_path / "job", clip, timeframe_start=5.0)
    assert not (tmp_path / "job" / META).exists()


def test_video_without_audio_is_an_error(make_media: MakeMedia, tmp_path: Path) -> None:
    silent = make_media("silent.mp4", "-c:v", "libx264", audio=False)
    with pytest.raises(StepError, match="silent.mp4 has no audio track"):
        ingest(tmp_path / "job", silent)
    assert not (tmp_path / "job" / META).exists()


def test_missing_source_file_is_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.mp4"
    with pytest.raises(StepError, match=f"source file not found: {missing}"):
        ingest(tmp_path / "job", missing)
