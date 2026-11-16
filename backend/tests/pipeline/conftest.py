"""Fixtures for the pipeline step tests."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from clipforge.config import RenderSettings
from clipforge.encoders import VIDEO_ENCODERS, VideoEncoder, available_encoders
from clipforge.ffmpeg import ffmpeg_bin, run_ffmpeg
from clipforge.pipeline import ingest
from clipforge.pipeline.step import (
    AUDIO,
    META,
    SOURCE,
    StepSettings,
    load_meta,
    write_json,
)

MakeMedia = Callable[..., Path]
CopyJob = Callable[..., Path]


@pytest.fixture(scope="module", params=VIDEO_ENCODERS)
def encoder(request: pytest.FixtureRequest) -> VideoEncoder:
    """Each H.264 encoder in turn (skipped where ffmpeg does not have it):
    the render tests pass with both."""
    name: VideoEncoder = request.param
    if name not in available_encoders(ffmpeg_bin()):
        pytest.skip(f"ffmpeg has no {name} encoder")
    return name


@pytest.fixture(scope="module")
def render_settings(encoder: VideoEncoder) -> RenderSettings:
    """The default render settings with encoder."""
    return RenderSettings(encoder=encoder)


@pytest.fixture(scope="session")
def make_media(tmp_path_factory: pytest.TempPathFactory) -> MakeMedia:
    """Return a function that encodes a short test file from ffmpeg's sources.

    make(name, *codec_args, size="320x240", audio=True, duration=1.0) writes
    name with a testsrc video of the given size (none if size is None) and a
    440 Hz tone (if audio), encoded with codec_args, and returns its path.
    audio_source replaces the tone with another lavfi audio source, such as
    "anullsrc=channel_layout=mono" for silence. testsrc keeps odd sizes;
    testsrc2 would round them down to even ones.
    """
    directory = tmp_path_factory.mktemp("media")

    def make(
        name: str,
        *codec_args: str,
        size: str | None = "320x240",
        audio: bool = True,
        audio_source: str = "sine=frequency=440",
        duration: float = 1.0,
    ) -> Path:
        inputs: list[str] = []
        if size is not None:
            video = f"testsrc=size={size}:rate=30:duration={duration}"
            inputs += ["-f", "lavfi", "-i", video]
        if audio:
            inputs += ["-f", "lavfi", "-i", f"{audio_source}:duration={duration}"]
        path = directory / name
        run_ffmpeg([*inputs, *codec_args, path])
        return path

    return make


@pytest.fixture(scope="session")
def two_scenes(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, float]:
    """A 4 s 320x240 30 fps h264/aac video with a 440 Hz tone, and the time
    of its one scene cut: testsrc for 2 s, then SMPTE color bars for 2 s."""
    cut = 2.0
    path = tmp_path_factory.mktemp("scenes") / "two_scenes.mp4"
    scene = f"size=320x240:rate=30:duration={cut}"
    run_ffmpeg(
        ["-f", "lavfi", "-i", f"testsrc={scene}"]
        + ["-f", "lavfi", "-i", f"smptebars={scene}"]
        + ["-f", "lavfi", "-i", f"sine=frequency=440:duration={2 * cut}"]
        + ["-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]"]
        + ["-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        + ["-c:a", "aac", path]
    )
    return path, cut


@pytest.fixture(scope="session")
def ingested_sample(sample_mp4: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A job in which ingest has run on the whole sample video.

    Tests share it, so they must not change it; copy_job makes copies.
    """
    job = tmp_path_factory.mktemp("ingested") / "job"
    ingest.run(job, StepSettings(source=str(sample_mp4)))
    return job


@pytest.fixture(scope="session")
def copy_job(
    ingested_sample: Path, tmp_path_factory: pytest.TempPathFactory
) -> CopyJob:
    """Return a function that copies ingested_sample into a new job directory.

    copy(start=0.0, end=60.0) copies its source.mp4, audio.wav and meta.json,
    with the timeframe [start, end] in meta.json, and returns the directory.
    """

    def copy(start: float = 0.0, end: float = 60.0) -> Path:
        job = tmp_path_factory.mktemp("job")
        for name in (SOURCE, AUDIO):
            shutil.copy(ingested_sample / name, job / name)
        meta = load_meta(ingested_sample)
        timeframe = {"timeframe_start": start, "timeframe_end": end}
        write_json(job / META, meta.model_copy(update=timeframe))
        return job

    return copy
