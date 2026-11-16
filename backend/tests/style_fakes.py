"""Fakes of the network for the style reference tests: canned yt-dlp pages
whose formats are file:// URLs of small generated files (the real yt-dlp
selects, downloads and merges them), a local file behind a direct link, and
generated test videos."""

import copy
from pathlib import Path
from typing import Any

import pytest
import yt_dlp
from clipforge.ffmpeg import run_ffmpeg
from clipforge.pipeline import download
from yt_dlp.utils import DownloadError

PAGE = "https://www.youtube.com/watch?v=styleref01"
LONG_PAGE = "https://www.youtube.com/watch?v=styleref02"
BROKEN_PAGE = "https://www.youtube.com/watch?v=styleref03"
DIRECT = "https://cdn.example/refs/phonk.mp4"
H264 = ("-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac")


def make_video(path: Path, size: str, seconds: float, rate: int = 30) -> Path:
    """Write a testsrc video with a tone of the given size and length."""
    video = f"testsrc=size={size}:rate={rate}:duration={seconds}"
    run_ffmpeg(
        ["-f", "lavfi", "-i", video]
        + ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
        + [*H264, "-shortest", path]
    )
    return path


class Web:
    """The canned pages yt-dlp sees, the local file behind DIRECT and the
    params of each YoutubeDL made."""

    def __init__(self) -> None:
        self.pages: dict[str, dict[str, Any]] = {}
        self.direct: Path | None = None
        self.params: list[dict[str, Any]] = []


@pytest.fixture(name="web")
def offline_web(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> Web:
    """Make downloads read local files instead of the network."""
    canned = Web()

    class OfflineYoutubeDL(yt_dlp.YoutubeDL):
        def __init__(self, params: Any = None, auto_init: bool = True) -> None:
            canned.params.append(dict(params or {}))
            super().__init__({**(params or {}), "enable_file_urls": True}, auto_init)

        def extract_info(self, url: str, download: bool = True, **_: Any) -> Any:
            if url == BROKEN_PAGE:
                raise DownloadError("Video unavailable")
            if url == DIRECT:
                assert canned.direct is not None
                return super().extract_info(canned.direct.as_uri(), download=download)
            page = copy.deepcopy(canned.pages[url])
            return self.process_ie_result(page, download=download)

    monkeypatch.setattr(download, "YoutubeDL", OfflineYoutubeDL)
    return canned


def page(duration: float | None, *formats: dict[str, Any]) -> dict[str, Any]:
    """The info dict of a single video page with the given formats."""
    return {
        "id": "styleref01",
        "title": "A reference",
        "duration": duration,
        "webpage_url": PAGE,
        "extractor": "generic",
        "extractor_key": "Generic",
        "formats": list(formats),
    }


def fmt(format_id: str, path: Path, height: int) -> dict[str, Any]:
    """A single-file format of height pixels served from path."""
    return {
        "format_id": format_id,
        "url": path.as_uri(),
        "ext": "mp4",
        "vcodec": "avc1",
        "acodec": "mp4a",
        "height": height,
    }


@pytest.fixture(name="small")
def small_reference(tmp_path: Path) -> Path:
    """A 1 s 320x240 reference."""
    return make_video(tmp_path / "small.mp4", "320x240", 1.0)
