"""Tests for the Dropbox source (clipforge.sources.dropbox): link parsing,
shared-link metadata and download with recorded Dropbox responses (respx),
the 401 refresh, error and short-download paths, and ingest of a link."""

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
from clipforge.sources import dropbox
from clipforge.sources.dropbox import DropboxError
from clipforge.token_store import TokenStore
from dropbox_fakes import (
    APP_KEY,
    LINK,
    OLD_ACCESS,
    configure_dropbox,
    json_response,
    metadata,
    store_token,
)


@pytest.fixture
def connected(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TokenStore:
    """Dropbox is configured and an account connected."""
    configure_dropbox(monkeypatch)
    return store_token()


def mock_dropbox(
    respx_mock: respx.MockRouter, video: bytes, meta: dict[str, object] | None = None
) -> tuple[respx.Route, respx.Route]:
    """Route the shared-link metadata (recorded) and file (video's bytes)."""
    info = respx_mock.post(dropbox.METADATA_URL).mock(
        return_value=httpx.Response(200, json=meta or metadata(len(video)))
    )
    media = respx_mock.post(dropbox.CONTENT_URL).mock(
        return_value=httpx.Response(200, content=video)
    )
    return info, media


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (LINK, LINK),
        (f"  {LINK}  ", LINK),
        (LINK.replace("https://www.", "http://"), LINK),
        (
            "https://dropbox.com/s/2sn712vy1ovegw8/Prime.mp4?dl=0#top",
            "https://www.dropbox.com/s/2sn712vy1ovegw8/Prime.mp4?dl=0",
        ),
    ],
)
def test_parse_link_reads_shared_file_links(text: str, expected: str) -> None:
    assert dropbox.parse_link(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "https://www.dropbox.com/sh/abc123/AAAxyz?dl=0",
        "https://www.dropbox.com/scl/fo/abc123/xyz?rlkey=k&dl=0",
        "https://www.dropbox.com/home/Videos",
        "https://evil.example.com/s/abc/talk.mp4",
        "https://www.dropbox.com.evil.example/s/abc/talk.mp4",
        "ftp://www.dropbox.com/s/abc/talk.mp4",
        "not a link",
    ],
)
def test_parse_link_rejects_folders_and_other_links(text: str) -> None:
    with pytest.raises(DropboxError) as bad:
        dropbox.parse_link(text)
    assert (bad.value.status, bad.value.code) == (422, "invalid_dropbox_link")


def test_dropbox_link_only_for_file_links() -> None:
    assert dropbox.dropbox_link(LINK) == LINK
    assert dropbox.dropbox_link("https://www.youtube.com/watch?v=x") is None
    assert dropbox.dropbox_link("https://www.dropbox.com/sh/abc/x") is None


def test_without_app_key_dropbox_needs_credentials(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_dropbox(monkeypatch, app_key="")
    store_token()
    assert dropbox.dropbox_client() is None
    assert not dropbox.is_connected()
    with pytest.raises(DropboxError) as missing:
        dropbox.dropbox_session()
    assert (missing.value.status, missing.value.code) == (412, "needs_credentials")
    assert "DROPBOX_APP_KEY" in missing.value.message


def test_dropbox_client_uses_the_verified_endpoints_and_scope(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_dropbox(monkeypatch)
    client = dropbox.dropbox_client()
    assert client is not None
    assert client.client_id == APP_KEY
    assert client.client_secret == ""
    assert client.authorize_url == "https://www.dropbox.com/oauth2/authorize"
    assert client.token_url == "https://api.dropboxapi.com/oauth2/token"
    assert client.scopes == ("sharing.read",)
    assert client.authorize_params == {"token_access_type": "offline"}


def test_get_file_reads_the_metadata(
    connected: TokenStore, respx_mock: respx.MockRouter
) -> None:
    info, _ = mock_dropbox(respx_mock, b"x" * 1234)

    found = dropbox.get_file(dropbox.dropbox_session(), LINK)

    assert found == dropbox.DropboxFile(
        url=LINK, name="Team offsite talk.mp4", size=1234
    )
    request = info.calls.last.request
    assert request.headers["authorization"] == f"Bearer {OLD_ACCESS}"
    assert json.loads(request.content) == {"url": LINK}


@pytest.mark.parametrize(
    ("status", "name", "code", "expected_status"),
    [
        (409, "error_not_found", "dropbox_file_not_found", 404),
        (409, "error_directory", "invalid_dropbox_link", 422),
        (429, "error_429", "dropbox_rate_limited", 429),
    ],
)
def test_get_file_maps_dropbox_errors(
    connected: TokenStore,
    respx_mock: respx.MockRouter,
    status: int,
    name: str,
    code: str,
    expected_status: int,
) -> None:
    respx_mock.post(dropbox.METADATA_URL).mock(return_value=json_response(status, name))
    with pytest.raises(DropboxError) as refused:
        dropbox.get_file(dropbox.dropbox_session(), LINK)
    assert (refused.value.status, refused.value.code) == (expected_status, code)


def test_get_file_with_a_plain_text_400_is_a_dropbox_error(
    connected: TokenStore, respx_mock: respx.MockRouter
) -> None:
    respx_mock.post(dropbox.METADATA_URL).mock(
        return_value=httpx.Response(400, text="Error in call to API function")
    )
    with pytest.raises(DropboxError) as refused:
        dropbox.get_file(dropbox.dropbox_session(), LINK)
    assert (refused.value.status, refused.value.code) == (502, "dropbox_error")
    assert "HTTP 400" in refused.value.message


@pytest.mark.parametrize(
    "changes", [{"name": "notes.pdf"}, {".tag": "folder", "name": "clips"}]
)
def test_get_file_rejects_what_is_not_a_video(
    connected: TokenStore, respx_mock: respx.MockRouter, changes: dict[str, object]
) -> None:
    mock_dropbox(respx_mock, b"x", metadata(1, **changes))
    with pytest.raises(DropboxError) as refused:
        dropbox.get_file(dropbox.dropbox_session(), LINK)
    assert (refused.value.status, refused.value.code) == (422, "not_a_video")


def test_a_401_refreshes_the_token_and_retries(
    connected: TokenStore, respx_mock: respx.MockRouter
) -> None:
    refresh = respx_mock.post(dropbox.TOKEN_URL).mock(
        return_value=json_response(200, "token_refresh")
    )
    info = respx_mock.post(dropbox.METADATA_URL).mock(
        side_effect=[
            json_response(401, "error_401"),
            httpx.Response(200, json=metadata(9)),
        ]
    )

    assert dropbox.get_file(dropbox.dropbox_session(), LINK).size == 9

    sent = parse_qs(refresh.calls.last.request.content.decode())
    assert sent["grant_type"] == ["refresh_token"]
    assert sent["client_id"] == [APP_KEY]
    assert "client_secret" not in sent
    assert info.calls.last.request.headers["authorization"] == (
        "Bearer sl.recorded-access-token-2"
    )
    saved = connected.load(dropbox.TOKEN_REF)
    assert saved is not None
    assert saved.access_token == "sl.recorded-access-token-2"
    assert saved.refresh_token == "recorded-dropbox-refresh-token"


def test_a_revoked_grant_disconnects_dropbox(
    connected: TokenStore, respx_mock: respx.MockRouter
) -> None:
    respx_mock.post(dropbox.TOKEN_URL).mock(
        return_value=json_response(400, "invalid_grant")
    )
    respx_mock.post(dropbox.METADATA_URL).mock(
        return_value=json_response(401, "error_401")
    )

    with pytest.raises(DropboxError) as revoked:
        dropbox.get_file(dropbox.dropbox_session(), LINK)

    assert (revoked.value.status, revoked.value.code) == (409, "dropbox_not_connected")
    assert connected.load(dropbox.TOKEN_REF) is None
    assert not dropbox.is_connected()


def test_download_streams_the_file_into_the_job_dir(
    connected: TokenStore, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    video = bytes(range(256)) * 9000
    _, media = mock_dropbox(respx_mock, video)
    progress: list[float] = []

    fetched = dropbox.download(LINK, tmp_path / "job", progress.append)

    assert fetched == Download(
        path=tmp_path / "job" / "download.mp4",
        title="Team offsite talk",
        channel=None,
        channel_url=None,
    )
    assert fetched.path.read_bytes() == video
    assert progress[-1] == 1.0 and progress == sorted(progress)
    request = media.calls.last.request
    assert request.method == "POST"
    assert json.loads(request.headers["dropbox-api-arg"]) == {"url": LINK}
    assert request.headers["authorization"] == f"Bearer {OLD_ACCESS}"
    assert not list((tmp_path / "job").glob("*.part"))


def test_a_short_download_fails_and_leaves_nothing(
    connected: TokenStore, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    mock_dropbox(respx_mock, b"only part", metadata(10_000))
    with pytest.raises(DropboxError) as short:
        dropbox.download(LINK, tmp_path / "job", lambda _: None)
    assert "stopped at 9 of 10000 bytes" in short.value.message
    assert list((tmp_path / "job").iterdir()) == []


def test_an_error_on_the_file_is_not_found(
    connected: TokenStore, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    respx_mock.post(dropbox.CONTENT_URL).mock(
        return_value=json_response(409, "error_not_found")
    )
    respx_mock.post(dropbox.METADATA_URL).mock(
        return_value=httpx.Response(200, json=metadata(5))
    )
    with pytest.raises(DropboxError) as missing:
        dropbox.download(LINK, tmp_path / "job", lambda _: None)
    assert missing.value.code == "dropbox_file_not_found"
    assert list((tmp_path / "job").iterdir()) == []


def test_ingest_downloads_a_dropbox_link_with_the_dropbox_api(
    connected: TokenStore,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
    sample_mp4: Path,
) -> None:
    mock_dropbox(respx_mock, sample_mp4.read_bytes())
    job_dir = tmp_path / "job"

    meta_path = ingest.run(job_dir, StepSettings(source=LINK))

    meta = SourceMeta.model_validate(json.loads(meta_path.read_text()))
    assert meta.title == "Team offsite talk"
    assert (job_dir / "source.mp4").is_file()
    assert not (job_dir / "download.mp4").exists()


def test_ingest_of_a_dropbox_link_without_a_connection_uses_yt_dlp(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sample_mp4: Path,
) -> None:
    configure_dropbox(monkeypatch)
    calls: list[str] = []

    def fake_download(url: str, job_dir: Path, on_progress: object) -> Download:
        calls.append(url)
        path = job_dir / "download.mp4"
        path.write_bytes(sample_mp4.read_bytes())
        return Download(path=path, title="public", channel=None, channel_url=None)

    monkeypatch.setattr(ingest, "download", fake_download)

    ingest.run(tmp_path, StepSettings(source=LINK))

    assert calls == [LINK]
