"""Tests for the Dropbox import endpoints (api/dropbox.py): 412 without the
app key, the connect + callback flow with a recorded token answer (respx),
the file lookup and the import that queues a project."""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from clipforge.sources import dropbox
from clipforge.token_store import TokenStore
from dropbox_fakes import (
    APP_KEY,
    LINK,
    configure_dropbox,
    json_response,
    metadata,
    store_token,
)
from fastapi.testclient import TestClient

CALLBACK = "http://testserver/api/sources/dropbox/callback"


@pytest.fixture
def configured(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The client of an app whose Dropbox app is configured."""
    configure_dropbox(monkeypatch)
    return client


def start_connect(client: TestClient) -> dict[str, str]:
    response = client.post("/api/sources/dropbox/connect")
    assert response.status_code == 200
    url = response.json()["authorize_url"]
    assert url.startswith(dropbox.AUTHORIZE_URL + "?")
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_status_without_credentials(client: TestClient) -> None:
    assert client.get("/api/sources/dropbox").json() == {
        "configured": False,
        "connected": False,
    }


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/sources/dropbox/connect", None),
        ("POST", "/api/sources/dropbox/file", {"file": LINK}),
        ("POST", "/api/sources/dropbox/import", {"file": LINK}),
    ],
)
def test_without_app_key_the_api_answers_412(
    client: TestClient, method: str, path: str, body: dict[str, str] | None
) -> None:
    store_token()
    response = client.request(method, path, json=body)
    assert response.status_code == 412
    assert response.json()["error"] == "needs_credentials"
    assert "DROPBOX_APP_KEY" in response.json()["message"]
    assert client.get("/api/projects").json() == []


def test_connect_then_callback_stores_the_token(
    configured: TestClient, respx_mock: respx.MockRouter
) -> None:
    token = respx_mock.post(dropbox.TOKEN_URL).mock(
        return_value=json_response(200, "token_exchange")
    )
    query = start_connect(configured)
    assert query["client_id"] == APP_KEY
    assert query["redirect_uri"] == CALLBACK
    assert query["scope"] == "sharing.read"
    assert query["token_access_type"] == "offline"
    assert query["code_challenge_method"] == "S256"
    assert configured.get("/api/sources/dropbox").json() == {
        "configured": True,
        "connected": False,
    }

    page = configured.get(
        "/api/sources/dropbox/callback",
        params={"state": query["state"], "code": "AUTH-CODE"},
    )

    assert page.status_code == 200
    assert "Dropbox is connected" in page.text
    assert "sl." not in page.text
    sent = parse_qs(token.calls.last.request.content.decode())
    assert sent["redirect_uri"] == [CALLBACK]
    assert sent["code"] == ["AUTH-CODE"]
    assert sent["code_verifier"]
    assert "client_secret" not in sent
    assert configured.get("/api/sources/dropbox").json()["connected"] is True
    saved = TokenStore.from_settings().load(dropbox.TOKEN_REF)
    assert saved is not None and saved.access_token == "sl.recorded-access-token-1"


def test_callback_with_an_unknown_state_or_a_denial_fails(
    configured: TestClient,
) -> None:
    unknown = configured.get(
        "/api/sources/dropbox/callback", params={"state": "forged", "code": "c"}
    )
    assert unknown.status_code == 400
    assert "unknown or expired" in unknown.text

    query = start_connect(configured)
    denied = configured.get(
        "/api/sources/dropbox/callback",
        params={"state": query["state"], "error": "access_denied"},
    )
    assert denied.status_code == 400
    assert "access was denied" in denied.text
    assert configured.get("/api/sources/dropbox").json()["connected"] is False


def test_callback_escapes_the_error_it_shows(configured: TestClient) -> None:
    query = start_connect(configured)
    page = configured.get(
        "/api/sources/dropbox/callback",
        params={"state": query["state"], "error": "<script>x</script>"},
    )
    assert "<script>" not in page.text
    assert "&lt;script&gt;" in page.text


def test_file_lookup_returns_the_video_or_404(
    configured: TestClient, respx_mock: respx.MockRouter
) -> None:
    store_token()
    route = respx_mock.post(dropbox.METADATA_URL).mock(
        side_effect=[
            httpx.Response(200, json=metadata(4096)),
            json_response(409, "error_not_found"),
        ]
    )

    found = configured.post("/api/sources/dropbox/file", json={"file": LINK})
    missing = configured.post("/api/sources/dropbox/file", json={"file": LINK})

    assert found.json() == {"url": LINK, "name": "Team offsite talk.mp4", "size": 4096}
    assert missing.status_code == 404
    assert missing.json()["error"] == "dropbox_file_not_found"
    assert route.call_count == 2


def test_file_lookup_of_a_bad_link_or_without_connection(
    configured: TestClient,
) -> None:
    folder = configured.post(
        "/api/sources/dropbox/file",
        json={"file": "https://www.dropbox.com/sh/abc123/AAAxyz?dl=0"},
    )
    assert folder.status_code == 422
    assert folder.json()["error"] == "invalid_dropbox_link"

    response = configured.post("/api/sources/dropbox/file", json={"file": LINK})
    assert response.status_code == 409
    assert response.json()["error"] == "dropbox_not_connected"


def test_import_queues_a_project_for_the_dropbox_link(
    configured: TestClient, respx_mock: respx.MockRouter
) -> None:
    store_token()
    respx_mock.post(dropbox.METADATA_URL).mock(
        return_value=httpx.Response(200, json=metadata(10))
    )

    response = configured.post(
        "/api/sources/dropbox/import",
        json={
            "file": LINK,
            "settings": {"num_clips": 3},
            "source_rights": "own",
            "credit_line": "Filmed by me",
        },
    )

    assert response.status_code == 201
    project = response.json()
    assert project["source_url"] == LINK
    assert project["source_rights"] == "own"
    assert project["credit_line"] == "Filmed by me"
    assert project["settings"]["num_clips"] == 3
    (job,) = configured.get(f"/api/projects/{project['id']}/jobs").json()
    assert (job["kind"], job["status"]) == ("process", "queued")


def test_import_of_a_missing_file_adds_nothing(
    configured: TestClient, respx_mock: respx.MockRouter
) -> None:
    store_token()
    respx_mock.post(dropbox.METADATA_URL).mock(
        return_value=json_response(409, "error_not_found")
    )
    response = configured.post("/api/sources/dropbox/import", json={"file": LINK})
    assert response.status_code == 404
    assert configured.get("/api/projects").json() == []


def test_disconnect_forgets_the_token(configured: TestClient, data_dir: Path) -> None:
    store_token()
    assert configured.get("/api/sources/dropbox").json()["connected"] is True

    assert configured.delete("/api/sources/dropbox/connection").status_code == 204

    assert configured.get("/api/sources/dropbox").json()["connected"] is False
    assert not list((data_dir / "oauth_tokens").iterdir())
