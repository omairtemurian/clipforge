"""The H.264 encoders (STEERING 2026-10-31): which ones ffmpeg has, the
default, their ffmpeg options, and the video_encoder setting."""

import subprocess
from collections.abc import Iterator
from typing import Any

import pytest
from clipforge import encoders
from clipforge.config import RenderSettings, Settings
from clipforge.encoders import (
    available_encoders,
    default_encoder,
    encoder_args,
    video_quality,
)

# The lines of `ffmpeg -hide_banner -encoders` around the H.264 encoders.
LISTING = """Encoders:
 V..... = Video
 ------
 V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC (codec h264)
 V....D libx264rgb           libx264 H.264 / AVC RGB (codec h264)
 V....D h264_videotoolbox    VideoToolbox H.264 Encoder (codec h264)
 A....D aac                  AAC (Advanced Audio Coding)
"""


@pytest.fixture(autouse=True)
def fresh_cache() -> Iterator[None]:
    available_encoders.cache_clear()
    yield
    available_encoders.cache_clear()


class FakeFfmpeg:
    """Stands in for subprocess.run: prints listing, or fails with error."""

    def __init__(self, listing: str = LISTING, error: Exception | None = None):
        self.listing, self.error = listing, error
        self.calls: list[list[str]] = []

    def __call__(
        self, command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(command, 0, self.listing, "")


def test_the_listed_encoders_are_read_once_per_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = FakeFfmpeg()
    monkeypatch.setattr(encoders.subprocess, "run", ffmpeg)

    assert available_encoders("/x/ffmpeg") == ("libx264", "h264_videotoolbox")
    assert available_encoders("/x/ffmpeg") == ("libx264", "h264_videotoolbox")
    assert default_encoder("/x/ffmpeg") == "h264_videotoolbox"

    assert ffmpeg.calls == [["/x/ffmpeg", "-hide_banner", "-encoders"]]


@pytest.mark.parametrize(
    "ffmpeg",
    [
        FakeFfmpeg(listing=LISTING.replace("h264_videotoolbox", "h264_vulkan")),
        FakeFfmpeg(error=FileNotFoundError("no ffmpeg")),
        FakeFfmpeg(error=subprocess.CalledProcessError(1, "ffmpeg")),
    ],
    ids=["not-listed", "missing", "failing"],
)
def test_without_videotoolbox_the_default_is_libx264(
    monkeypatch: pytest.MonkeyPatch, ffmpeg: FakeFfmpeg
) -> None:
    monkeypatch.setattr(encoders.subprocess, "run", ffmpeg)

    assert available_encoders("ffmpeg") == ("libx264",)
    assert default_encoder("ffmpeg") == "libx264"


@pytest.mark.parametrize(
    ("crf", "quality"), [(0, 100), (18, 75), (20, 70), (23, 62), (28, 50), (51, 1)]
)
def test_videotoolbox_quality_follows_the_crf(crf: int, quality: int) -> None:
    assert video_quality(crf) == quality


def test_each_encoder_gets_its_own_options() -> None:
    assert encoder_args("libx264", "medium", 20) == [
        *("-c:v", "libx264", "-preset", "medium", "-crf", "20"),
    ]
    assert encoder_args("h264_videotoolbox", "medium", 20) == [
        *("-c:v", "h264_videotoolbox", "-q:v", "70"),
    ]


@pytest.mark.parametrize(
    ("listing", "expected"),
    [(LISTING, "h264_videotoolbox"), ("", "libx264")],
)
def test_an_unset_video_encoder_is_the_default_of_the_ffmpeg_in_use(
    monkeypatch: pytest.MonkeyPatch, listing: str, expected: str
) -> None:
    ffmpeg = FakeFfmpeg(listing)
    monkeypatch.setattr(encoders.subprocess, "run", ffmpeg)

    cfg = Settings(ffmpeg_bin="/y/ffmpeg", video_encoder="")

    assert cfg.video_encoder == expected
    assert ffmpeg.calls == [["/y/ffmpeg", "-hide_banner", "-encoders"]]
    assert cfg.render_settings() == RenderSettings(encoder=expected)


def test_a_set_video_encoder_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    ffmpeg = FakeFfmpeg()
    monkeypatch.setattr(encoders.subprocess, "run", ffmpeg)
    monkeypatch.setenv("VIDEO_ENCODER", "libx264")

    assert Settings().video_encoder == "libx264"
    assert Settings(video_encoder="h264_videotoolbox").video_encoder == (
        "h264_videotoolbox"
    )
    assert ffmpeg.calls == []


def test_an_unknown_video_encoder_is_refused() -> None:
    with pytest.raises(ValueError, match="video_encoder"):
        Settings(video_encoder="h264_nvenc")
