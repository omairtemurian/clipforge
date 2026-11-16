"""Recorded Google responses and helpers of the Google Drive import tests.

The JSON files in fixtures/gdrive follow the shapes of Google's docs
(2026-10-31): the token endpoint's answer in "OAuth 2.0 for iOS & Desktop
Apps" (a refresh answer has no refresh_token), the File resource of Drive
API v3 (`size` is an int64 string; "SIZE" becomes the sample video's size)
and the 401 authError / 404 notFound bodies of "Resolve errors". The ids and
tokens are made up.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from clipforge import config
from clipforge.oauth_tokens import Token
from clipforge.sources import gdrive
from clipforge.token_store import TokenStore

GDRIVE_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gdrive"
CLIENT_ID = "1234567890-test.apps.googleusercontent.com"
CLIENT_SECRET = "GOCSPX-test-secret"
FILE_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
FILE_URL = f"{gdrive.FILES_URL}/{FILE_ID}"
OLD_ACCESS = "ya29.a0-old-access-token"
OLD_REFRESH = "1//0g-recorded-refresh-token"


def recorded(name: str, **replace: object) -> dict[str, Any]:
    """Return the recorded JSON fixtures/gdrive/<name>.json; a value equal to
    a key of replace (e.g. "SIZE") is replaced by its value."""
    data: dict[str, Any] = json.loads((GDRIVE_FIXTURES / f"{name}.json").read_text())
    return {k: replace.get(v, v) if isinstance(v, str) else v for k, v in data.items()}


def metadata(size: int, **changes: object) -> dict[str, Any]:
    """The recorded file metadata with the given size and changes."""
    return {**recorded("file_metadata", SIZE=str(size)), **changes}


def configure_google(
    monkeypatch: pytest.MonkeyPatch, client_id: str = CLIENT_ID
) -> None:
    """Set the Google OAuth app in config.settings (keeps its data_dir)."""
    cfg = config.settings.model_copy(
        update={
            "google_oauth_client_id": client_id,
            "google_oauth_client_secret": CLIENT_SECRET if client_id else "",
        }
    )
    monkeypatch.setattr(config, "settings", cfg)


def store_token(expires_at: float | None = None) -> TokenStore:
    """Save a connected account's token (OLD_ACCESS) and return the store."""
    store = TokenStore.from_settings()
    store.save(
        gdrive.TOKEN_REF,
        Token(
            access_token=OLD_ACCESS,
            refresh_token=OLD_REFRESH,
            expires_at=expires_at,
            scope=gdrive.DRIVE_SCOPE,
        ),
    )
    return store


def json_response(status: int, name: str) -> httpx.Response:
    """A response with the recorded JSON body fixtures/gdrive/<name>.json."""
    return httpx.Response(status, json=recorded(name))
