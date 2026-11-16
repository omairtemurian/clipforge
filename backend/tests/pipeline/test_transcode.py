"""Tests of pipeline/transcode: converting an ingested video to h264/aac with
the configured encoder (libx264 when a hardware encoder fails) and reporting
the conversion's progress, in the ingest step's band and in the log.
"""

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from clipforge import config
from clipforge.encoders import HARDWARE, SOFTWARE, VideoEncoder, encoder_args
from clipforge.ffmpeg import Arg, FFmpegError, probe_media
from clipforge.models import ProcessingSettings
from clipforge.pipeline import ingest, transcode
from clipforge.pipeline.step import SOURCE, StepSettings
from clipforge.pipeline.transcode import VIDEO_LABEL, write_source

MakeMedia = Callable[..., Path]
VP9_OPUS = (
    "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
    "-c:a", "libopus",
)  # fmt: skip
BROKEN = ["-c:v", "clipforge_no_such_encoder"]


@pytest.fixture(scope="module")
def vp9_webm(make_media: MakeMedia) -> Path:
    """A 2 s VP9/Opus webm, like a YouTube download without H.264."""
    return make_media("vp9-opus.webm", *VP9_OPUS, size="322x180", duration=2.0)


def video_encoders(commands: list[list[str]]) -> list[str]:
    """The -c:v value of each recorded ffmpeg command."""
    return [args[args.index("-c:v") + 1] for args in commands]


@pytest.fixture
def commands(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record the args of every conversion ffmpeg run (which still runs)."""
    recorded: list[list[str]] = []
    real = transcode.run_ffmpeg_progress

    def spy(
        args: Sequence[Arg], duration: float, on_progress: Callable[[float], None]
    ) -> None:
        recorded.append([str(arg) for arg in args])
        real(args, duration, on_progress)

    monkeypatch.setattr(transcode, "run_ffmpeg_progress", spy)
    return recorded


def break_encoders(monkeypatch: pytest.MonkeyPatch, *broken: VideoEncoder) -> None:
    """Make the encoders in broken name an encoder ffmpeg does not have."""

    def args(encoder: VideoEncoder, preset: str, crf: int) -> list[str]:
        return BROKEN if encoder in broken else encoder_args(encoder, preset, crf)

    monkeypatch.setattr(transcode, "encoder_args", args)


def test_vp9_opus_is_converted_with_the_encoder_and_reports_progress(
    vp9_webm: Path,
    encoder: VideoEncoder,
    commands: list[list[str]],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=transcode.__name__)
    progress: list[float] = []
    dst = tmp_path / SOURCE
    write_source(
        vp9_webm, dst, move=False, encoder=encoder, on_progress=progress.append
    )
    info = probe_media(dst)
    assert (info.video_codec, info.pix_fmt, info.audio_codec) == (
        "h264",
        "yuv420p",
        "aac",
    )
    assert (info.width, info.height) == (322, 180)
    assert video_encoders(commands) == [encoder]
    assert progress[0] == 0.0 and progress[-1] == 1.0
    assert progress == sorted(progress)
    lines = [
        r.getMessage() for r in caplog.records if r.getMessage().startswith(VIDEO_LABEL)
    ]
    assert lines[0] == "Converting video to H.264: 0%"
    assert lines[-1] == "Converting video to H.264: 100%"
    assert len(lines) == len(set(lines))
    assert vp9_webm.is_file()


def test_failing_hardware_encoder_falls_back_to_libx264(
    vp9_webm: Path,
    commands: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    break_encoders(monkeypatch, HARDWARE)
    progress: list[float] = []
    dst = tmp_path / SOURCE
    write_source(
        vp9_webm, dst, move=False, encoder=HARDWARE, on_progress=progress.append
    )
    assert probe_media(dst).video_codec == "h264"
    assert video_encoders(commands) == [BROKEN[1], SOFTWARE]
    assert f"{HARDWARE} failed" in caplog.text
    assert f"converting with {SOFTWARE}" in caplog.text
    assert progress[0] == 0.0 and progress[-1] == 1.0
    assert not dst.with_suffix(".tmp.mp4").exists()


def test_failing_libx264_is_an_error_without_a_retry(
    vp9_webm: Path,
    commands: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    break_encoders(monkeypatch, SOFTWARE)
    dst = tmp_path / SOURCE
    with pytest.raises(FFmpegError, match="exited with status"):
        write_source(vp9_webm, dst, move=False, encoder=SOFTWARE)
    assert video_encoders(commands) == [BROKEN[1]]
    assert list(tmp_path.iterdir()) == []


def test_h264_with_mp3_only_converts_the_audio(
    make_media: MakeMedia,
    commands: list[list[str]],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=transcode.__name__)
    mp4 = make_media(
        "h264-mp3.mp4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "libmp3lame"
    )
    progress: list[float] = []
    write_source(
        mp4,
        tmp_path / SOURCE,
        move=False,
        encoder=HARDWARE,
        on_progress=progress.append,
    )
    assert video_encoders(commands) == ["copy"]
    assert progress[0] == 0.0 and progress[-1] == 1.0
    assert "Converting audio to AAC: 100%" in caplog.text
    assert VIDEO_LABEL not in caplog.text


def test_unchanged_mp4_reports_no_conversion(
    sample_mp4: Path, commands: list[list[str]], tmp_path: Path
) -> None:
    progress: list[float] = []
    write_source(sample_mp4, tmp_path / SOURCE, move=False, on_progress=progress.append)
    assert (commands, progress) == ([], [])


def test_ingest_converts_with_the_configured_encoder_in_its_progress_band(
    vp9_webm: Path, commands: list[list[str]], tmp_path: Path
) -> None:
    cfg = config.settings.model_copy(update={"video_encoder": SOFTWARE})
    progress: list[float] = []
    settings = StepSettings(
        source=str(vp9_webm),
        processing=ProcessingSettings(),
        cfg=cfg,
        on_progress=progress.append,
    )
    ingest.run(tmp_path / "job", settings)
    assert video_encoders(commands) == [SOFTWARE]
    band = [p for p in progress if ingest.CONVERT_START <= p <= ingest.SOURCE_READY]
    assert band[0] == ingest.CONVERT_START
    assert band[-1] == pytest.approx(ingest.SOURCE_READY)
    assert progress == sorted(progress) and progress[-1] == 1.0
    assert all(p < ingest.CONVERT_START for p in progress[: progress.index(band[0])])
