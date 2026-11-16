"""Tests for the Google Drive import endpoints (api/gdrive.py): 412 without
credentials, the connect + callback flow with a recorded token answer
(respx), the file lookup and the import that queues a project."""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from clipforge.sources import gdrive
from clipforge.token_store import TokenStore
from fastapi.testclient import TestClient
from gdrive_fakes import (
    CLIENT_ID,
    FILE_ID,
    FILE_URL,
    configure_google,
    json_response,
    metadata,
    store_token,
)

CALLBACK = "http://testserver/api/sources/gdrive/callback"


@pytest.fixture
def google(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The client of an app whose Google OAuth app is configured."""
    configure_google(monkeypatch)
    return client


def start_connect(client: TestClient) -> dict[str, str]:
    response = client.post("/api/sources/gdrive/connect")
    assert response.status_code == 200
    url = response.json()["authorize_url"]
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_status_without_credentials(client: TestClient) -> None:
    assert client.get("/api/sources/gdrive").json() == {
        "configured": False,
        "connected": False,
    }


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/sources/gdrive/connect", None),
        ("POST", "/api/sources/gdrive/file", {"file": FILE_ID}),
        ("POST", "/api/sources/gdrive/import", {"file": FILE_ID}),
    ],
)
def test_without_client_id_the_api_answers_412(
    client: TestClient, method: str, path: str, body: dict[str, str] | None
) -> None:
    store_token()
    response = client.request(method, path, json=body)
    assert response.status_code == 412
    assert response.json()["error"] == "needs_credentials"
    assert "GOOGLE_OAUTH_CLIENT_ID" in response.json()["message"]
    assert client.get("/api/projects").json() == []


def test_connect_then_callback_stores_the_token(
    google: TestClient, respx_mock: respx.MockRouter
) -> None:
    token = respx_mock.post(gdrive.TOKEN_URL).mock(
        return_value=json_response(200, "token_exchange")
    )
    query = start_connect(google)
    assert query["client_id"] == CLIENT_ID
    assert query["redirect_uri"] == CALLBACK
    assert query["scope"] == gdrive.DRIVE_SCOPE
    assert google.get("/api/sources/gdrive").json() == {
        "configured": True,
        "connected": False,
    }

    page = google.get(
        "/api/sources/gdrive/callback", params={"state": query["state"], "code": "4/c"}
    )

    assert page.status_code == 200
    assert "Google Drive is connected" in page.text
    assert "ya29" not in page.text
    sent = parse_qs(token.calls.last.request.content.decode())
    assert sent["redirect_uri"] == [CALLBACK]
    assert sent["code"] == ["4/c"]
    assert google.get("/api/sources/gdrive").json()["connected"] is True
    saved = TokenStore.from_settings().load(gdrive.TOKEN_REF)
    assert saved is not None and saved.access_token == "ya29.a0-recorded-access-token-1"


def test_callback_with_an_unknown_state_or_a_denial_fails(google: TestClient) -> None:
    unknown = google.get(
        "/api/sources/gdrive/callback", params={"state": "forged", "code": "4/c"}
    )
    assert unknown.status_code == 400
    assert "unknown or expired" in unknown.text

    query = start_connect(google)
    denied = google.get(
        "/api/sources/gdrive/callback",
        params={"state": query["state"], "error": "access_denied"},
    )
    assert denied.status_code == 400
    assert "access was denied" in denied.text
    assert google.get("/api/sources/gdrive").json()["connected"] is False


def test_callback_escapes_the_error_it_shows(google: TestClient) -> None:
    query = start_connect(google)
    page = google.get(
        "/api/sources/gdrive/callback",
        params={"state": query["state"], "error": "<script>x</script>"},
    )
    assert "<script>" not in page.text
    assert "&lt;script&gt;" in page.text


def test_file_lookup_returns_the_video_or_404(
    google: TestClient, respx_mock: respx.MockRouter
) -> None:
    store_token()
    route = respx_mock.get(FILE_URL).mock(
        side_effect=[
            httpx.Response(200, json=metadata(4096)),
            json_response(404, "error_404"),
        ]
    )
    link = f"https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing"

    found = google.post("/api/sources/gdrive/file", json={"file": link})
    missing = google.post("/api/sources/gdrive/file", json={"file": FILE_ID})

    assert found.json() == {
        "id": FILE_ID,
        "name": "Team offsite talk.mp4",
        "mime_type": "video/mp4",
        "size": 4096,
        "duration": 60.033,
    }
    assert missing.status_code == 404
    assert missing.json()["error"] == "drive_file_not_found"
    assert route.call_count == 2


def test_file_lookup_of_a_bad_link_or_without_connection(google: TestClient) -> None:
    folder = google.post(
        "/api/sources/gdrive/file",
        json={"file": "https://drive.google.com/drive/folders/1AbCdEfGhIjKl"},
    )
    assert folder.status_code == 422
    assert folder.json()["error"] == "invalid_drive_link"

    response = google.post("/api/sources/gdrive/file", json={"file": FILE_ID})
    assert response.status_code == 409
    assert response.json()["error"] == "drive_not_connected"


def test_import_queues_a_project_for_the_drive_link(
    google: TestClient, respx_mock: respx.MockRouter
) -> None:
    store_token()
    respx_mock.get(FILE_URL).mock(return_value=httpx.Response(200, json=metadata(10)))

    response = google.post(
        "/api/sources/gdrive/import",
        json={
            "file": FILE_ID,
            "settings": {"num_clips": 3},
            "source_rights": "own",
            "credit_line": "Filmed by me",
        },
    )

    assert response.status_code == 201
    project = response.json()
    assert project["source_url"] == gdrive.file_url(FILE_ID)
    assert project["source_rights"] == "own"
    assert project["credit_line"] == "Filmed by me"
    assert project["settings"]["num_clips"] == 3
    (job,) = google.get(f"/api/projects/{project['id']}/jobs").json()
    assert (job["kind"], job["status"]) == ("process", "queued")


def test_import_of_a_missing_file_adds_nothing(
    google: TestClient, respx_mock: respx.MockRouter
) -> None:
    store_token()
    respx_mock.get(FILE_URL).mock(return_value=json_response(404, "error_404"))
    response = google.post("/api/sources/gdrive/import", json={"file": FILE_ID})
    assert response.status_code == 404
    assert google.get("/api/projects").json() == []


def test_disconnect_forgets_the_token(google: TestClient, data_dir: Path) -> None:
    store_token()
    assert google.get("/api/sources/gdrive").json()["connected"] is True

    assert google.delete("/api/sources/gdrive/connection").status_code == 204

    assert google.get("/api/sources/gdrive").json()["connected"] is False
    assert not list((data_dir / "oauth_tokens").iterdir())
