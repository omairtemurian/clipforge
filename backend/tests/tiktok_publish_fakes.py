"""Recorded TikTok API answers and helpers of the TikTok publisher tests
(tests only).

The JSON files in fixtures/tiktok_publish follow the shapes of TikTok's
API reference (2026-11-01): {data, error: {code, message, log_id}} of
user/info, creator_info/query, video/init and status/fetch (PROCESSING_UPLOAD,
PUBLISH_COMPLETE with publicaly_available_post_id, FAILED with
fail_reason), the error codes of the Direct Post reference and the token
endpoint's answers. The ids and tokens are made up.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from clipforge import config, posts
from clipforge.models import Post
from clipforge.oauth_tokens import Token
from clipforge.publishers import tiktok
from clipforge.publishers.publish import publish_post
from clipforge.token_store import TokenStore
from social_fakes import add_account
from sqlalchemy import Engine
from youtube_publish_fakes import write_sized_video

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tiktok_publish"
CLIENT_KEY = "awx1cliplabkey"
CLIENT_SECRET = "tt-cliplab-secret"
OPEN_ID = "723f24d7-e717-40f8-a2b6-cb8464cd23b4"
PUBLISH_ID = "v_pub_file~v2-1.7412345678901234567"
POST_ID = "7412345678901234567"
UPLOAD_URL = (
    "https://open-upload.tiktokapis.com/video/"
    "?upload_id=7412345678901&upload_token=Xza9f3c1"
)
ACCESS = "act.cliplab-access-0001"
REFRESH = "rft.cliplab-refresh-0001"
NOW = datetime(2026, 11, 1, 7, 30, tzinfo=UTC)
CHUNK = 1024
# Two chunks: 1024 bytes and a last one of 1576 (with the trailing bytes).
VIDEO_SIZE = 2600


def recorded(name: str) -> dict[str, Any]:
    """Return the recorded JSON fixtures/tiktok_publish/<name>.json."""
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text())
    return data


def answer(status: int, name: str) -> httpx.Response:
    """A recorded answer with the given status."""
    return httpx.Response(status, json=recorded(name))


def tiktok_settings(client_key: str = CLIENT_KEY) -> config.Settings:
    """The app settings with a TikTok app (keeps the data_dir)."""
    return config.settings.model_copy(
        update={
            "tiktok_client_key": client_key,
            "tiktok_client_secret": CLIENT_SECRET if client_key else "",
        }
    )


def configure_tiktok(
    monkeypatch: pytest.MonkeyPatch, client_key: str = CLIENT_KEY
) -> None:
    """Set the TikTok app in config.settings ("" : not configured)."""
    monkeypatch.setattr(config, "settings", tiktok_settings(client_key))


def make_publisher(sleeps: list[float] | None = None) -> tiktok.TikTokPublisher:
    """A publisher with CHUNK-byte chunks whose clock says NOW and whose
    sleeps are recorded instead of waited."""
    client = tiktok.tiktok_client(tiktok_settings())
    assert client is not None
    waits = sleeps if sleeps is not None else []
    return tiktok.TikTokPublisher(
        client, clock=NOW.timestamp, sleep=waits.append, chunk_bytes=CHUNK
    )


def queue_tiktok_post(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    payload: dict[str, Any] | None = None,
) -> int:
    """Queue a post of clip_id to a connected TikTok account (its token
    stored) and return its id."""
    account_id = add_account(engine, OPEN_ID, "tiktok")
    store.save(
        f"ref-{OPEN_ID}",
        Token(access_token=ACCESS, refresh_token=REFRESH, expires_at=None),
    )
    post = posts.create_post(
        engine,
        clip_id=clip_id,
        account_id=account_id,
        payload=payload
        if payload is not None
        else {"caption": "A clip", "privacy_level": "SELF_ONLY"},
    )
    return posts.queue_post(engine, post.id).id


def publish_tiktok(
    engine: Engine, post_id: int, store: TokenStore, **kwargs: Any
) -> Post:
    """Publish the post with a test TikTokPublisher."""
    publisher = make_publisher(**kwargs)
    return publish_post(engine, post_id, store, lambda _platform: publisher)


def ready_tiktok_post(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    payload: dict[str, Any] | None = None,
) -> int:
    """Write the clip's video and queue its TikTok post."""
    write_sized_video(engine, clip_id, VIDEO_SIZE)
    return queue_tiktok_post(engine, clip_id, store, payload)


def mock_direct_post(
    respx_mock: respx.MockRouter,
    creator: httpx.Response | None = None,
    init: httpx.Response | None = None,
    put: Any = None,
    status: Any = None,
) -> dict[str, respx.Route]:
    """Mock the four Direct Post calls (default: everything works)."""
    return {
        "creator": respx_mock.post(tiktok.CREATOR_INFO_URL).mock(
            return_value=creator or answer(200, "creator_info")
        ),
        "init": respx_mock.post(tiktok.INIT_URL).mock(
            return_value=init or answer(200, "video_init")
        ),
        "put": respx_mock.put(UPLOAD_URL).mock(
            side_effect=put or [httpx.Response(206), httpx.Response(201)]
        ),
        "status": respx_mock.post(tiktok.STATUS_URL).mock(
            side_effect=status
            or [answer(200, "status_processing"), answer(200, "status_complete")]
        ),
    }
