"""Tests for the Google Drive source (clipforge.sources.gdrive): link parsing,
files.get metadata and alt=media download with recorded Google responses
(respx), the 401 refresh and 404 paths, and ingest of a Drive link."""

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from clipforge.models import SourceMeta
from clipforge.pipeline import ingest
from clipforge.pipeline.download import Download
from clipforge.pipeline.step import StepSettings
from clipforge.sources import gdrive
from clipforge.sources.gdrive import DriveError
from clipforge.token_store import TokenStore
from gdrive_fakes import (
    CLIENT_ID,
    FILE_ID,
    FILE_URL,
    OLD_ACCESS,
    configure_google,
    json_response,
    metadata,
    store_token,
)


@pytest.fixture
def connected(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TokenStore:
    """Google is configured and an account connected."""
    configure_google(monkeypatch)
    return store_token()


def mock_drive(
    respx_mock: respx.MockRouter, video: bytes, meta: dict[str, object] | None = None
) -> tuple[respx.Route, respx.Route]:
    """Route files.get: metadata (recorded) and media (video's bytes)."""
    media = respx_mock.get(FILE_URL, params={"alt": "media"}).mock(
        return_value=httpx.Response(200, content=video)
    )
    info = respx_mock.get(FILE_URL).mock(
        return_value=httpx.Response(200, json=meta or metadata(len(video)))
    )
    return info, media


@pytest.mark.parametrize(
    "text",
    [
        FILE_ID,
        f"https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing",
        f"https://drive.google.com/file/d/{FILE_ID}",
        f"https://drive.google.com/open?id={FILE_ID}",
        f"https://drive.google.com/uc?id={FILE_ID}&export=download",
        f"https://drive.usercontent.google.com/download?id={FILE_ID}",
        f"https://docs.google.com/file/d/{FILE_ID}/edit",
        f"  https://drive.google.com/u/0/file/d/{FILE_ID}/view  ",
    ],
)
def test_parse_file_id_reads_links_and_ids(text: str) -> None:
    assert gdrive.parse_file_id(text) == FILE_ID


@pytest.mark.parametrize(
    "text",
    [
        "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://drive.google.com/open?id=short",
        "not a link",
    ],
)
def test_parse_file_id_rejects_folders_and_other_links(text: str) -> None:
    with pytest.raises(DriveError) as bad:
        gdrive.parse_file_id(text)
    assert (bad.value.status, bad.value.code) == (422, "invalid_drive_link")


def test_drive_file_id_only_for_drive_links() -> None:
    assert gdrive.drive_file_id(gdrive.file_url(FILE_ID)) == FILE_ID
    assert gdrive.drive_file_id("https://www.youtube.com/watch?v=x") is None
    assert gdrive.drive_file_id("https://drive.google.com/drive/folders/x") is None


def test_without_client_id_drive_needs_credentials(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_google(monkeypatch, client_id="")
    store_token()
    assert gdrive.google_client() is None
    assert not gdrive.is_connected()
    with pytest.raises(DriveError) as missing:
        gdrive.drive_session()
    assert (missing.value.status, missing.value.code) == (412, "needs_credentials")


def test_google_client_uses_the_verified_endpoints_and_scope(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_google(monkeypatch)
    client = gdrive.google_client()
    assert client is not None
    assert client.client_id == CLIENT_ID
    assert client.authorize_url == "https://accounts.google.com/o/oauth2/v2/auth"
    assert client.token_url == "https://oauth2.googleapis.com/token"
    assert client.scopes == ("https://www.googleapis.com/auth/drive.readonly",)


def test_get_file_reads_the_metadata(
    connected: TokenStore, respx_mock: respx.MockRouter
) -> None:
    info, _ = mock_drive(respx_mock, b"x" * 1234)

    found = gdrive.get_file(gdrive.drive_session(), FILE_ID)

    assert found == gdrive.DriveFile(
        id=FILE_ID,
        name="Team offsite talk.mp4",
        mime_type="video/mp4",
        size=1234,
        duration=60.033,
    )
    request = info.calls.last.request
    assert request.headers["authorization"] == f"Bearer {OLD_ACCESS}"
    assert dict(request.url.params) == {
        "fields": gdrive.METADATA_FIELDS,
        "supportsAllDrives": "true",
    }


def test_get_file_404_is_not_found(
    connected: TokenStore, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(FILE_URL).mock(return_value=json_response(404, "error_404"))
    with pytest.raises(DriveError) as missing:
        gdrive.get_file(gdrive.drive_session(), FILE_ID)
    assert (missing.value.status, missing.value.code) == (404, "drive_file_not_found")


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"mimeType": "application/pdf"}, "not_a_video"),
        ({"capabilities": {"canDownload": False}}, "drive_file_not_downloadable"),
    ],
)
def test_get_file_rejects_what_cannot_be_imported(
    connected: TokenStore,
    respx_mock: respx.MockRouter,
    changes: dict[str, object],
    code: str,
) -> None:
    mock_drive(respx_mock, b"x", metadata(1, **changes))
    with pytest.raises(DriveError) as refused:
        gdrive.get_file(gdrive.drive_session(), FILE_ID)
    assert (refused.value.status, refused.value.code) == (422, code)


def test_a_401_refreshes_the_token_and_retries(
    connected: TokenStore, respx_mock: respx.MockRouter
) -> None:
    refresh = respx_mock.post(gdrive.TOKEN_URL).mock(
        return_value=json_response(200, "token_refresh")
    )
    info = respx_mock.get(FILE_URL).mock(
        side_effect=[
            json_response(401, "error_401"),
            httpx.Response(200, json=metadata(9)),
        ]
    )

    assert gdrive.get_file(gdrive.drive_session(), FILE_ID).size == 9

    sent = parse_qs(refresh.calls.last.request.content.decode())
    assert sent["grant_type"] == ["refresh_token"]
    assert sent["client_id"] == [CLIENT_ID]
    assert info.calls.last.request.headers["authorization"] == (
        "Bearer ya29.a0-recorded-access-token-2"
    )
    saved = connected.load(gdrive.TOKEN_REF)
    assert saved is not None
    assert saved.access_token == "ya29.a0-recorded-access-token-2"
    assert saved.refresh_token == "1//0g-recorded-refresh-token"


def test_a_revoked_grant_disconnects_drive(
    connected: TokenStore, respx_mock: respx.MockRouter
) -> None:
    respx_mock.post(gdrive.TOKEN_URL).mock(
        return_value=json_response(400, "invalid_grant")
    )
    respx_mock.get(FILE_URL).mock(return_value=json_response(401, "error_401"))

    with pytest.raises(DriveError) as revoked:
        gdrive.get_file(gdrive.drive_session(), FILE_ID)

    assert (revoked.value.status, revoked.value.code) == (409, "drive_not_connected")
    assert connected.load(gdrive.TOKEN_REF) is None
    assert not gdrive.is_connected()


def test_download_streams_the_media_into_the_job_dir(
    connected: TokenStore, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    video = bytes(range(256)) * 9000
    _, media = mock_drive(respx_mock, video)
    progress: list[float] = []

    fetched = gdrive.download(FILE_ID, tmp_path / "job", progress.append)

    assert fetched == Download(
        path=tmp_path / "job" / "download.mp4",
        title="Team offsite talk",
        channel=None,
        channel_url=None,
    )
    assert fetched.path.read_bytes() == video
    assert progress[-1] == 1.0 and progress == sorted(progress)
    assert dict(media.calls.last.request.url.params) == {
        "alt": "media",
        "supportsAllDrives": "true",
    }
    assert not list((tmp_path / "job").glob("*.part"))


def test_a_short_download_fails_and_leaves_nothing(
    connected: TokenStore, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    mock_drive(respx_mock, b"only part", metadata(10_000))
    with pytest.raises(DriveError) as short:
        gdrive.download(FILE_ID, tmp_path / "job", lambda _: None)
    assert "stopped at 9 of 10000 bytes" in short.value.message
    assert list((tmp_path / "job").iterdir()) == []


def test_a_404_on_the_media_is_not_found(
    connected: TokenStore, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    respx_mock.get(FILE_URL, params={"alt": "media"}).mock(
        return_value=json_response(404, "error_404")
    )
    respx_mock.get(FILE_URL).mock(return_value=httpx.Response(200, json=metadata(5)))
    with pytest.raises(DriveError) as missing:
        gdrive.download(FILE_ID, tmp_path / "job", lambda _: None)
    assert missing.value.code == "drive_file_not_found"
    assert list((tmp_path / "job").iterdir()) == []


def test_ingest_downloads_a_drive_link_with_the_drive_api(
    connected: TokenStore,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
    sample_mp4: Path,
) -> None:
    mock_drive(respx_mock, sample_mp4.read_bytes())
    job_dir = tmp_path / "job"

    meta_path = ingest.run(job_dir, StepSettings(source=gdrive.file_url(FILE_ID)))

    meta = SourceMeta.model_validate(json.loads(meta_path.read_text()))
    assert meta.title == "Team offsite talk"
    assert (job_dir / "source.mp4").is_file()
    assert not (job_dir / "download.mp4").exists()


def test_ingest_of_a_drive_link_without_a_connection_uses_yt_dlp(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sample_mp4: Path,
) -> None:
    configure_google(monkeypatch)
    calls: list[str] = []

    def fake_download(url: str, job_dir: Path, on_progress: object) -> Download:
        calls.append(url)
        path = job_dir / "download.mp4"
        path.write_bytes(sample_mp4.read_bytes())
        return Download(path=path, title="public", channel=None, channel_url=None)

    monkeypatch.setattr(ingest, "download", fake_download)
    url = gdrive.file_url(FILE_ID)

    ingest.run(tmp_path, StepSettings(source=url))

    assert calls == [url]
