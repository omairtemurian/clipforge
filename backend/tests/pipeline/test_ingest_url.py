"""Tests of the ingest step with URL sources.

They run the real yt-dlp: format selection, the download, the ffmpeg merge
and the progress hooks. Only extraction, the part that reads web pages, is
replaced: extract_info returns a canned page whose formats are file:// URLs
of local test files.
"""

import copy
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yt_dlp
from clipforge.ffmpeg import probe_media
from clipforge.models import SourceMeta
from clipforge.pipeline import download
from clipforge.pipeline.download import ytdlp_options
from clipforge.pipeline.ingest import AUDIO, DOWNLOADED, META, SOURCE, THUMB, run
from clipforge.pipeline.step import StepError, StepSettings
from clipforge.pipeline.ytdlp_session import SIGN_IN_MESSAGE
from yt_dlp.utils import DownloadError

MakeMedia = Callable[..., Path]
URL = "https://www.youtube.com/watch?v=clipforge01"
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLclipforge"
CHANNEL = ("Sample Comedian", "https://www.youtube.com/@SampleComedian")
OUTPUTS = sorted((SOURCE, AUDIO, THUMB, META))


@dataclass
class Web:
    """The canned pages yt-dlp sees, and the params of each YoutubeDL made."""

    pages: dict[str, dict[str, Any]] = field(default_factory=dict)
    params: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch) -> Web:
    """Make ingest use a YoutubeDL that extracts URLs from web.pages."""
    canned = Web()

    class OfflineYoutubeDL(yt_dlp.YoutubeDL):
        def __init__(self, params: Any = None, auto_init: bool = True) -> None:
            canned.params.append(dict(params or {}))
            super().__init__({**(params or {}), "enable_file_urls": True}, auto_init)

        def extract_info(self, url: str, download: bool = True, **_: Any) -> Any:
            page = copy.deepcopy(canned.pages[url])
            return self.process_ie_result(page, download=download)

    monkeypatch.setattr(download, "YoutubeDL", OfflineYoutubeDL)
    return canned


@pytest.fixture(scope="module")
def media(make_media: MakeMedia) -> dict[str, Path]:
    """Files for the formats of a video page: separate streams and a single file."""
    h264 = ("-c:v", "libx264", "-pix_fmt", "yuv420p")
    return {
        "video": make_media("video-720.mp4", *h264, size="1280x720", audio=False),
        "audio": make_media("audio.m4a", "-c:a", "aac", size=None),
        "single": make_media("single-360.mp4", *h264, "-c:a", "aac", size="640x360"),
    }


def fmt(format_id: str, path: Path, ext: str, **fields: Any) -> dict[str, Any]:
    """A format entry of an info dict, served from the local file path."""
    return {"format_id": format_id, "url": path.as_uri(), "ext": ext, **fields}


def page(*formats: dict[str, Any]) -> dict[str, Any]:
    """The info dict of a single video page with the given formats."""
    return {
        "id": "clipforge01",
        "title": "Big Laugh Special",
        "channel": CHANNEL[0],
        "channel_url": CHANNEL[1],
        "webpage_url": URL,
        "extractor": "generic",
        "extractor_key": "Generic",
        "formats": list(formats),
    }


def youtube_like_page(media: dict[str, Path], missing: Path) -> dict[str, Any]:
    """A page with a 360p single file, 720p and 2160p video, and an audio stream."""
    return page(
        fmt("18", media["single"], "mp4", vcodec="avc1", acodec="mp4a", height=360),
        fmt("136", media["video"], "mp4", vcodec="avc1", acodec="none", height=720),
        fmt("401", missing, "mp4", vcodec="av01", acodec="none", height=2160),
        fmt("140", media["audio"], "m4a", vcodec="none", acodec="mp4a", abr=128),
    )


def ingest_url(job_dir: Path, url: str = URL) -> tuple[SourceMeta, list[float]]:
    """Run ingest on url; return the meta.json it wrote and its progress."""
    progress: list[float] = []
    meta = run(job_dir, StepSettings(source=url, on_progress=progress.append))
    return SourceMeta.model_validate_json(meta.read_text()), progress


def test_url_is_downloaded_with_the_spec_format_and_merged_into_an_mp4(
    web: Web, media: dict[str, Path], tmp_path: Path
) -> None:
    web.pages[URL] = youtube_like_page(media, tmp_path / "missing-2160.mp4")
    job_dir = tmp_path / "job"
    meta, progress = ingest_url(job_dir)

    (params,) = web.params
    assert params["format"] == "bv*[height<=1080]+ba/b[height<=1080]"
    assert params["merge_output_format"] == "mp4"
    assert params["paths"] == {"home": str(job_dir)}
    assert sorted(path.name for path in job_dir.iterdir()) == OUTPUTS
    info = probe_media(job_dir / SOURCE)
    assert (info.width, info.height) == (1280, 720)
    assert (info.video_codec, info.audio_codec) == ("h264", "aac")
    assert (meta.title, meta.channel, meta.channel_url) == (
        "Big Laugh Special",
        *CHANNEL,
    )
    assert (meta.width, meta.height) == (1280, 720)
    assert progress == sorted(progress)
    assert any(0 < value <= DOWNLOADED for value in progress)
    assert progress[-1] == 1.0


def test_single_file_up_to_1080p_is_used_without_separate_streams(
    web: Web, media: dict[str, Path], tmp_path: Path
) -> None:
    web.pages[URL] = page(
        fmt(
            "37",
            tmp_path / "missing-1440.mp4",
            "mp4",
            vcodec="avc1",
            acodec="mp4a",
            height=1440,
        ),
        fmt("18", media["single"], "mp4", vcodec="avc1", acodec="mp4a", height=360),
    )
    meta, _ = ingest_url(tmp_path / "job")
    assert (meta.width, meta.height) == (640, 360)


def test_url_without_formats_up_to_1080p_is_an_error(
    web: Web, media: dict[str, Path], tmp_path: Path
) -> None:
    web.pages[URL] = page(
        fmt(
            "401",
            tmp_path / "missing.mp4",
            "mp4",
            vcodec="av01",
            acodec="none",
            height=2160,
        ),
        fmt("140", media["audio"], "m4a", vcodec="none", acodec="mp4a", abr=128),
    )
    with pytest.raises(StepError, match="download failed: .*format is not available"):
        ingest_url(tmp_path / "job")
    assert not (tmp_path / "job" / META).exists()


def test_failed_download_is_an_error(web: Web, tmp_path: Path) -> None:
    gone = tmp_path / "gone.mp4"
    web.pages[URL] = page(
        fmt("22", gone, "mp4", vcodec="avc1", acodec="mp4a", height=720)
    )
    with pytest.raises(StepError, match=r"^download failed: .*No such file"):
        ingest_url(tmp_path / "job")
    assert not (tmp_path / "job" / META).exists()


def test_sign_in_video_asks_for_browser_cookies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class AgeGatedYoutubeDL(yt_dlp.YoutubeDL):
        def extract_info(self, url: str, download: bool = True, **_: Any) -> Any:
            raise DownloadError(
                "ERROR: [youtube] clipforge01: Sign in to confirm your age. "
                "Use --cookies-from-browser or --cookies for the authentication."
            )

    monkeypatch.setattr(download, "YoutubeDL", AgeGatedYoutubeDL)
    with pytest.raises(StepError) as raised:
        ingest_url(tmp_path / "job")
    assert str(raised.value) == SIGN_IN_MESSAGE


def test_playlist_is_rejected_before_anything_is_downloaded(
    web: Web, tmp_path: Path
) -> None:
    web.pages[PLAYLIST_URL] = {
        "_type": "playlist",
        "id": "PLclipforge",
        "title": "Best of",
        "webpage_url": PLAYLIST_URL,
        "extractor": "generic",
        "extractor_key": "Generic",
        "entries": [{"_type": "url", "url": URL, "ie_key": "Generic"}],
    }
    with pytest.raises(StepError, match="is a playlist, not a single video"):
        ingest_url(tmp_path / "job", PLAYLIST_URL)
    assert list((tmp_path / "job").iterdir()) == []


def test_ytdlp_options_are_documented_by_the_installed_yt_dlp(tmp_path: Path) -> None:
    doc = yt_dlp.YoutubeDL.__doc__ or ""
    options: Mapping[str, Any] = ytdlp_options(tmp_path, lambda event: None)
    for key in options:
        assert re.search(rf"^    {key}:", doc, re.MULTILINE), key
    for event_key in ("downloaded_bytes", "total_bytes", "total_bytes_estimate"):
        assert f"* {event_key}:" in doc, event_key
