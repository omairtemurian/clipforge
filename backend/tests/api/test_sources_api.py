"""Endpoints of the Home settings panel: link probes (presets and subtitles
are in test_presets_api and test_subtitles_api).

yt-dlp runs for real (its processing of an info dict, thumbnails and format
selection); only extraction, the part that reads web pages, is replaced by
canned pages, so nothing goes to the network.
"""

import copy
from typing import Any

import pytest
import yt_dlp
from apihelpers import assert_error
from clipforge.pipeline import download
from fastapi.testclient import TestClient
from yt_dlp.utils import DownloadError

URL = "https://www.youtube.com/watch?v=clipforge01"
PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLclipforge"
DEAD_URL = "https://www.youtube.com/watch?v=gone"
AGE_GATED_URL = "https://www.youtube.com/watch?v=jLbst85USN8"
AGE_GATE = (
    "ERROR: [youtube] jLbst85USN8: Sign in to confirm your age. This video may "
    "be inappropriate for some users. Use --cookies-from-browser or --cookies"
)


def video_page(**fields: Any) -> dict[str, Any]:
    """The info dict of a single video page."""
    return {
        "id": "clipforge01",
        "title": "Big Laugh Special",
        "duration": 754,
        "webpage_url": URL,
        "extractor": "generic",
        "extractor_key": "Generic",
        "thumbnails": [
            {"url": "https://img.example/small.jpg", "preference": -5},
            {"url": "https://img.example/large.jpg", "preference": 1},
        ],
        "formats": [
            {"format_id": "18", "url": "https://media.example/v.mp4", "ext": "mp4"}
        ],
        **fields,
    }


@pytest.fixture
def pages(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    """Make probes read the canned pages; an unknown URL fails like yt-dlp."""
    canned: dict[str, dict[str, Any]] = {}

    class OfflineYoutubeDL(yt_dlp.YoutubeDL):
        def extract_info(self, url: str, download: bool = True, **_: Any) -> Any:
            if url == AGE_GATED_URL:
                raise DownloadError(AGE_GATE)
            if url not in canned:
                raise DownloadError("ERROR: [generic] gone: Video unavailable")
            return self.process_ie_result(copy.deepcopy(canned[url]), download)

    monkeypatch.setattr(download, "YoutubeDL", OfflineYoutubeDL)
    return canned


def test_probe_reads_title_duration_and_best_thumbnail(
    client: TestClient, pages: dict[str, dict[str, Any]]
) -> None:
    pages[URL] = video_page()

    response = client.post("/api/sources/probe", json={"url": f"  {URL} "})

    assert response.status_code == 200
    assert response.json() == {
        "url": URL,
        "title": "Big Laugh Special",
        "duration": 754.0,
        "thumbnail_url": "https://img.example/large.jpg",
    }


def test_probe_without_duration_or_thumbnail_gives_nulls_and_ytdlp_title(
    client: TestClient, pages: dict[str, dict[str, Any]]
) -> None:
    pages[URL] = video_page(duration=None, thumbnails=[], title="")

    body = client.post("/api/sources/probe", json={"url": URL}).json()

    assert body["title"] == "generic video #clipforge01"
    assert body["duration"] is None
    assert body["thumbnail_url"] is None


def test_probe_rejects_a_playlist(
    client: TestClient, pages: dict[str, dict[str, Any]]
) -> None:
    pages[PLAYLIST_URL] = {
        "_type": "playlist",
        "id": "PLclipforge",
        "title": "Best of",
        "webpage_url": PLAYLIST_URL,
        "extractor": "generic",
        "extractor_key": "Generic",
        "entries": [{"_type": "url", "url": URL, "ie_key": "Generic"}],
    }

    response = client.post("/api/sources/probe", json={"url": PLAYLIST_URL})

    message = assert_error(response, 422, "probe_failed")
    assert "is a playlist, not a single video" in message


def test_probe_reports_why_a_page_cannot_be_read(
    client: TestClient, pages: dict[str, dict[str, Any]]
) -> None:
    response = client.post("/api/sources/probe", json={"url": DEAD_URL})

    message = assert_error(response, 422, "probe_failed")
    assert message == "cannot read the video page: [generic] gone: Video unavailable"


def test_probe_of_a_sign_in_video_asks_for_browser_cookies(
    client: TestClient, pages: dict[str, dict[str, Any]]
) -> None:
    response = client.post("/api/sources/probe", json={"url": AGE_GATED_URL})

    message = assert_error(response, 422, "probe_failed")
    assert message == (
        "This video needs a signed-in YouTube session. Set 'Browser cookies' "
        "in Settings (e.g. chrome) and retry."
    )


def test_probe_rejects_a_site_without_an_extractor(client: TestClient) -> None:
    response = client.post(
        "/api/sources/probe", json={"url": "https://example.com/talks/big-laugh"}
    )

    message = assert_error(response, 422, "unsupported_source")
    assert message.startswith("example.com is not a supported video site")


def test_probe_reads_a_vimeo_link(
    client: TestClient, pages: dict[str, dict[str, Any]]
) -> None:
    vimeo = "https://vimeo.com/76979871"
    pages[vimeo] = video_page(webpage_url=vimeo, title="The New Vimeo Player")

    response = client.post("/api/sources/probe", json={"url": vimeo})

    assert response.status_code == 200
    assert response.json()["title"] == "The New Vimeo Player"


@pytest.mark.parametrize("url", ["ftp://example.com/v.mp4", "/Users/me/v.mp4", ""])
def test_probe_accepts_only_web_links(client: TestClient, url: str) -> None:
    response = client.post("/api/sources/probe", json={"url": url})

    assert "http(s) URL" in assert_error(response, 422, "validation_error")
