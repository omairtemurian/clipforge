"""Recorded Dropbox responses and helpers of the Dropbox import tests.

The JSON files in fixtures/dropbox follow the shapes of Dropbox's API spec
(2026-11-01): the token endpoint's answer (a refresh answer has no
refresh_token), the FileLinkMetadata of sharing/get_shared_link_metadata
("SIZE" becomes the sample video's size) and the error bodies
({"error_summary", "error": {".tag"}}). The link, ids and tokens are made up.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from clipforge import config
from clipforge.oauth_tokens import Token
from clipforge.sources import dropbox
from clipforge.token_store import TokenStore

DROPBOX_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dropbox"
APP_KEY = "test-app-key-1234"
LINK = "https://www.dropbox.com/scl/fi/abc123xyz/Team-offsite-talk.mp4?rlkey=k3yk3yk3y&dl=0"
OLD_ACCESS = "sl.old-access-token"
OLD_REFRESH = "recorded-dropbox-refresh-token"


def recorded(name: str, **replace: object) -> dict[str, Any]:
    """Return the recorded JSON fixtures/dropbox/<name>.json; a value equal
    to a key of replace (e.g. "SIZE") is replaced by its value."""
    data: dict[str, Any] = json.loads((DROPBOX_FIXTURES / f"{name}.json").read_text())
    return {k: replace.get(v, v) if isinstance(v, str) else v for k, v in data.items()}


def metadata(size: int, **changes: object) -> dict[str, Any]:
    """The recorded link metadata with the given size and changes."""
    return {**recorded("link_metadata", SIZE=size), **changes}


def configure_dropbox(monkeypatch: pytest.MonkeyPatch, app_key: str = APP_KEY) -> None:
    """Set the Dropbox app in config.settings (keeps its data_dir)."""
    cfg = config.settings.model_copy(
        update={
            "dropbox_app_key": app_key,
            "dropbox_app_secret": "unused-secret" if app_key else "",
        }
    )
    monkeypatch.setattr(config, "settings", cfg)


def store_token(expires_at: float | None = None) -> TokenStore:
    """Save a connected account's token (OLD_ACCESS) and return the store."""
    store = TokenStore.from_settings()
    store.save(
        dropbox.TOKEN_REF,
        Token(
            access_token=OLD_ACCESS,
            refresh_token=OLD_REFRESH,
            expires_at=expires_at,
            scope=dropbox.SCOPE,
        ),
    )
    return store


def json_response(status: int, name: str) -> httpx.Response:
    """A response with the recorded JSON body fixtures/dropbox/<name>.json."""
    return httpx.Response(status, json=recorded(name))
