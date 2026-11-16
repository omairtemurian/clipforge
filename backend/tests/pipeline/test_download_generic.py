"""Tests of URL sources other than YouTube (SPEC-v2 3.1).

Which sites are supported is read from the installed yt-dlp's extractors. The
downloads run the real yt-dlp (format selection, the generic extractor, the
download, the ffmpeg merge); only the network is replaced: a link to a media
file is served from a local file:// URL, and a Vimeo page is a canned info
dict whose formats are local files.
"""

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yt_dlp
from clipforge.ffmpeg import probe_media
from clipforge.models import SourceMeta
from clipforge.pipeline import download, extractors
from clipforge.pipeline.extractors import (
    UnsupportedSource,
    extractor_for,
    is_direct_media,
    require_supported,
)
from clipforge.pipeline.ingest import META, SOURCE, run
from clipforge.pipeline.step import StepSettings
from yt_dlp.extractor.common import InfoExtractor

MakeMedia = Callable[..., Path]
VIMEO_URL = "https://vimeo.com/76979871"
ZOOM_URL = "https://us02web.zoom.us/rec/share/abcDEF123-xyz"
DIRECT_URL = "https://cdn.example/talks/big-laugh.mp4"
PAGE_URL = "https://example.com/talks/big-laugh"


@pytest.fixture(scope="module")
def clip_file(make_media: MakeMedia) -> Path:
    """A 1 s 640x360 h264/aac video."""
    h264 = ("-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac")
    return make_media("generic-360.mp4", *h264, size="640x360")


@pytest.fixture
def offline(
    monkeypatch: pytest.MonkeyPatch, clip_file: Path
) -> dict[str, dict[str, Any]]:
    """Make downloads read local files instead of the network.

    A link in the returned dict is extracted from its canned info dict;
    DIRECT_URL is extracted by yt-dlp's real generic extractor from the
    file:// URL of clip_file.
    """
    pages: dict[str, dict[str, Any]] = {}

    class OfflineYoutubeDL(yt_dlp.YoutubeDL):
        def __init__(self, params: Any = None, auto_init: bool = True) -> None:
            super().__init__({**(params or {}), "enable_file_urls": True}, auto_init)

        def extract_info(self, url: str, download: bool = True, **_: Any) -> Any:
            if url in pages:
                page = copy.deepcopy(pages[url])
                return self.process_ie_result(page, download=download)
            local = clip_file.as_uri() if url == DIRECT_URL else url
            return super().extract_info(local, download=download)

    monkeypatch.setattr(download, "YoutubeDL", OfflineYoutubeDL)
    return pages


def ingest_url(job_dir: Path, url: str) -> tuple[SourceMeta, list[float]]:
    """Run ingest on url; return the meta.json it wrote and its progress."""
    progress: list[float] = []
    meta = run(job_dir, StepSettings(source=url, on_progress=progress.append))
    return SourceMeta.model_validate_json(meta.read_text()), progress


@pytest.mark.parametrize(
    ("url", "name"),
    [
        (VIMEO_URL, "vimeo"),
        (ZOOM_URL, "zoom"),
        ("https://www.dropbox.com/s/abc/talk.mp4?dl=0", "Dropbox"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
    ],
)
def test_installed_ytdlp_has_an_extractor_for_these_sites(url: str, name: str) -> None:
    assert extractor_for(url) == name
    assert require_supported(url) == name


@pytest.mark.parametrize("url", [PAGE_URL, "https://example.com/", DIRECT_URL])
def test_only_the_generic_extractor_matches_an_unknown_site(url: str) -> None:
    assert extractor_for(url) is None


def test_support_follows_the_installed_extractor_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ClipHostIE(InfoExtractor):
        IE_NAME = "cliphost"
        _VALID_URL = r"https?://clips\.example/v/(?P<id>\w+)"

    url = "https://clips.example/v/abc123"
    with pytest.raises(UnsupportedSource):
        require_supported(url)

    monkeypatch.setattr(extractors, "list_extractor_classes", lambda: [ClipHostIE])
    assert require_supported(url) == "cliphost"
    with pytest.raises(UnsupportedSource):
        require_supported(VIMEO_URL)


def test_extractors_that_yt_dlp_marks_not_working_are_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenIE(InfoExtractor):
        IE_NAME = "broken"
        _WORKING = False
        _VALID_URL = r"https?://broken\.example/.*"

    monkeypatch.setattr(extractors, "list_extractor_classes", lambda: [BrokenIE])
    assert extractor_for("https://broken.example/v/1") is None


@pytest.mark.parametrize(
    "url",
    [
        DIRECT_URL,
        "https://cdn.example/a.MOV?token=1",
        "https://cdn.example/audio/talk.m4a",
        "https://cdn.example/live/index.m3u8",
    ],
)
def test_a_link_to_a_media_file_is_supported_by_the_generic_extractor(
    url: str,
) -> None:
    assert is_direct_media(url)
    assert require_supported(url) == "generic"


@pytest.mark.parametrize("url", [PAGE_URL, "https://example.com/a.html", "https://x.y"])
def test_a_page_of_an_unknown_site_is_unsupported_with_a_message(url: str) -> None:
    with pytest.raises(UnsupportedSource, match="not a supported video site"):
        require_supported(url)


def test_unsupported_link_is_rejected_before_yt_dlp_runs(
    offline: dict[str, dict[str, Any]], tmp_path: Path
) -> None:
    with pytest.raises(UnsupportedSource, match=r"^example\.com is not a supported"):
        ingest_url(tmp_path / "job", PAGE_URL)
    with pytest.raises(UnsupportedSource):
        download.probe(PAGE_URL)
    assert not (tmp_path / "job" / META).exists()


def test_direct_video_link_is_ingested_with_the_real_generic_extractor(
    offline: dict[str, dict[str, Any]], tmp_path: Path
) -> None:
    job_dir = tmp_path / "job"
    meta, progress = ingest_url(job_dir, DIRECT_URL)

    info = probe_media(job_dir / SOURCE)
    assert (info.width, info.height) == (640, 360)
    assert (info.video_codec, info.audio_codec) == ("h264", "aac")
    assert meta.title == "generic-360"
    assert progress[-1] == 1.0


def test_vimeo_link_is_ingested_with_its_title_and_channel(
    offline: dict[str, dict[str, Any]], clip_file: Path, tmp_path: Path
) -> None:
    offline[VIMEO_URL] = {
        "id": "76979871",
        "title": "The New Vimeo Player",
        "uploader": "Vimeo Staff",
        "uploader_url": "https://vimeo.com/staff",
        "webpage_url": VIMEO_URL,
        "extractor": "vimeo",
        "extractor_key": "Vimeo",
        "formats": [
            {
                "format_id": "http-360p",
                "url": clip_file.as_uri(),
                "ext": "mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
                "height": 360,
            }
        ],
    }
    job_dir = tmp_path / "job"
    meta, _ = ingest_url(job_dir, VIMEO_URL)

    assert (meta.title, meta.channel, meta.channel_url) == (
        "The New Vimeo Player",
        "Vimeo Staff",
        "https://vimeo.com/staff",
    )
    assert probe_media(job_dir / SOURCE).height == 360
