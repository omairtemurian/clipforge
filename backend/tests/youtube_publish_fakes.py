"""Recorded YouTube Data API answers and helpers of the YouTube publisher
tests (tests only).

The JSON files in fixtures/youtube_publish follow the shapes of YouTube's
reference (2026-11-01): the channel list (snippet, status), the video
resource that the upload answers (status.uploadStatus uploaded/rejected),
thumbnails.set's thumbnailSetResponse and the error body {error: {code,
message, errors: [{domain, reason, message}]}} with reasons of the errors
page (quotaExceeded, rateLimitExceeded, forbiddenPrivacySetting, authError,
backendError). The ids and tokens are made up.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from clipforge import config, posts
from clipforge.asset_rows import UsageRecordRow
from clipforge.oauth_tokens import Token
from clipforge.publishers import youtube
from clipforge.publishers.youtube_upload import CHUNK_UNIT, UPLOAD_URL
from clipforge.token_store import TokenStore
from social_fakes import add_account, clip_of
from sqlalchemy import Engine, func
from sqlmodel import Session, col, select

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "youtube_publish"
CHANNEL_ID = "UCa1B2c3D4e5F6g7H8i9J0kL"
VIDEO_ID = "dQ8wX4yZ1aB"
SESSION_URL = f"{UPLOAD_URL}?uploadType=resumable&upload_id=xa298sd_f"
ACCESS = "ya29.a0-youtube-access"
REFRESH = "1//0g-youtube-refresh"
# 2026-11-01 00:30 in Los Angeles (PDT, the day DST ends).
NOW = datetime(2026, 11, 1, 7, 30, tzinfo=UTC)
# Two whole chunks of 256 KiB and a last one of 90 KiB.
VIDEO_SIZE = 2 * CHUNK_UNIT + 90 * 1024


def recorded(name: str) -> dict[str, Any]:
    """Return the recorded JSON fixtures/youtube_publish/<name>.json."""
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text())
    return data


def answer(status: int, name: str) -> httpx.Response:
    """A recorded answer with the given status."""
    return httpx.Response(status, json=recorded(name))


def session_started() -> httpx.Response:
    """The answer that starts a resumable upload session."""
    return httpx.Response(200, headers={"Location": SESSION_URL})


def received(last: int | None) -> httpx.Response:
    """308 Resume Incomplete: bytes 0..last arrived (None: nothing yet)."""
    headers = {} if last is None else {"Range": f"bytes=0-{last}"}
    return httpx.Response(308, headers=headers)


def google_settings() -> config.Settings:
    """The app settings with a Google OAuth app (keeps the data_dir)."""
    return config.settings.model_copy(
        update={
            "google_oauth_client_id": "1234567890-yt.apps.googleusercontent.com",
            "google_oauth_client_secret": "GOCSPX-yt-secret",
        }
    )


def make_publisher(sleeps: list[float] | None = None) -> youtube.YouTubePublisher:
    """A publisher with 256 KiB chunks whose clock says NOW and whose sleeps
    are recorded instead of waited."""
    client = youtube.youtube_client(google_settings())
    assert client is not None
    waits = sleeps if sleeps is not None else []
    return youtube.YouTubePublisher(
        client,
        clock=NOW.timestamp,
        sleep=waits.append,
        chunk_bytes=CHUNK_UNIT,
    )


def queue_youtube_post(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    payload: dict[str, Any] | None = None,
    **fields: Any,
) -> int:
    """Queue a post of clip_id to a connected YouTube channel (its token
    stored) and return its id."""
    account_id = add_account(engine, CHANNEL_ID, "youtube")
    store.save(
        f"ref-{CHANNEL_ID}",
        Token(access_token=ACCESS, refresh_token=REFRESH, expires_at=None),
    )
    post = posts.create_post(
        engine,
        clip_id=clip_id,
        account_id=account_id,
        payload=payload if payload is not None else {"title": "A clip"},
        **fields,
    )
    return posts.queue_post(engine, post.id).id


def write_sized_video(engine: Engine, clip_id: int, size: int = VIDEO_SIZE) -> bytes:
    """Write size bytes as the clip's rendered video and return them."""
    clip = clip_of(engine, clip_id)
    assert clip.output_path is not None
    data = bytes(i % 251 for i in range(size))
    Path(clip.output_path).write_bytes(data)
    return data


def units_used(engine: Engine, kind: str) -> float:
    """Return the usage units recorded of kind."""
    with Session(engine) as session:
        total = session.exec(
            select(func.sum(UsageRecordRow.units)).where(
                col(UsageRecordRow.kind) == kind
            )
        ).one()
    return float(total or 0)
