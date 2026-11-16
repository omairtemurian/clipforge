"""Tests for the TikTok publisher's upload (clipforge.publishers.tiktok)
through the publish run, against recorded TikTok answers (respx): the
creator check, the init request with its post settings, the chunked
upload and the post status, interrupted chunks and a 401 token refresh
(refusals: test_tiktok_refusals.py). Nothing reaches the network."""

import json

import httpx
import respx
from clipforge.publishers import registry, tiktok
from clipforge.publishers.tiktok_api import MAX_CHUNK_RETRIES
from clipforge.token_store import TokenStore
from sqlalchemy import Engine
from tiktok_publish_fakes import (
    ACCESS,
    CLIENT_KEY,
    OPEN_ID,
    POST_ID,
    PUBLISH_ID,
    VIDEO_SIZE,
    answer,
    mock_direct_post,
    publish_tiktok,
    queue_tiktok_post,
    ready_tiktok_post,
    recorded,
)
from youtube_publish_fakes import write_sized_video

PAYLOAD = {
    "caption": "The one habit that changed everything #habits",
    "privacy_level": "PUBLIC_TO_EVERYONE",
    "allow_comment": True,
    "allow_stitch": True,
    "cover_timestamp_ms": 1500,
    "ai_generated": True,
}


def test_a_post_checks_the_creator_then_uploads_in_chunks(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    data = write_sized_video(engine, clip_id, VIDEO_SIZE)
    post_id = queue_tiktok_post(engine, clip_id, store, PAYLOAD)
    routes = mock_direct_post(respx_mock)
    sleeps: list[float] = []

    post = publish_tiktok(engine, post_id, store, sleeps=sleeps)

    assert (post.status, post.external_post_id, post.error) == (
        "published",
        POST_ID,
        None,
    )
    assert post.url == f"https://www.tiktok.com/@cliplab/video/{POST_ID}"
    creator = routes["creator"].calls.last.request
    assert creator.headers["authorization"] == f"Bearer {ACCESS}"
    assert creator.headers["content-type"] == "application/json; charset=UTF-8"
    init = routes["init"].calls.last.request
    assert init.headers["content-type"] == "application/json; charset=UTF-8"
    assert json.loads(init.content) == {
        "post_info": {
            "title": "The one habit that changed everything #habits",
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_comment": False,
            "disable_duet": True,
            "disable_stitch": True,
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
            "is_aigc": True,
            "video_cover_timestamp_ms": 1500,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": VIDEO_SIZE,
            "chunk_size": 1024,
            "total_chunk_count": 2,
        },
    }
    puts = [call.request for call in routes["put"].calls]
    assert [r.headers["content-range"] for r in puts] == [
        f"bytes 0-1023/{VIDEO_SIZE}",
        f"bytes 1024-{VIDEO_SIZE - 1}/{VIDEO_SIZE}",
    ]
    assert [r.headers["content-type"] for r in puts] == ["video/mp4"] * 2
    assert all("authorization" not in r.headers for r in puts)
    assert b"".join(r.content for r in puts) == data
    assert [json.loads(c.request.content) for c in routes["status"].calls] == [
        {"publish_id": PUBLISH_ID}
    ] * 2
    assert sleeps == [tiktok.STATUS_WAIT_S] * 2


def test_a_private_post_keeps_its_publish_id(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_tiktok_post(engine, clip_id, store)
    mock_direct_post(respx_mock, status=[answer(200, "status_complete_private")])

    post = publish_tiktok(engine, post_id, store)

    assert (post.status, post.external_post_id, post.url) == (
        "published",
        PUBLISH_ID,
        None,
    )


def test_a_post_still_processing_counts_as_sent(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_tiktok_post(engine, clip_id, store)
    routes = mock_direct_post(
        respx_mock, status=lambda _r: answer(200, "status_processing")
    )

    post = publish_tiktok(engine, post_id, store)

    assert (post.status, post.external_post_id) == ("published", PUBLISH_ID)
    assert routes["status"].call_count == tiktok.STATUS_POLLS


def test_interrupted_chunks_are_sent_again(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_tiktok_post(engine, clip_id, store)
    routes = mock_direct_post(
        respx_mock,
        put=[
            httpx.Response(206),
            httpx.ReadError("connection reset"),
            httpx.Response(503),
            httpx.Response(201),
        ],
    )
    sleeps: list[float] = []

    post = publish_tiktok(engine, post_id, store, sleeps=sleeps)

    assert post.status == "published"
    ranges = [c.request.headers["content-range"] for c in routes["put"].calls]
    assert ranges[1:] == [f"bytes 1024-{VIDEO_SIZE - 1}/{VIDEO_SIZE}"] * 3
    assert sleeps[:2] == [2.0, 4.0]


def test_an_upload_interrupted_too_often_is_retried_later(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_tiktok_post(engine, clip_id, store)
    mock_direct_post(respx_mock, put=httpx.ConnectError("offline"))
    sleeps: list[float] = []

    post = publish_tiktok(engine, post_id, store, sleeps=sleeps)

    assert post.status == "queued"
    assert post.error == "The upload to TikTok was interrupted too often."
    assert sleeps == [float(2**n) for n in range(1, MAX_CHUNK_RETRIES + 1)]


def test_a_401_refreshes_the_token_with_the_client_key(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_tiktok_post(engine, clip_id, store)
    token = respx_mock.post(tiktok.TOKEN_URL).mock(
        return_value=answer(200, "token_refreshed")
    )
    routes = mock_direct_post(respx_mock)
    routes["creator"].side_effect = [
        answer(401, "error_access_token_invalid"),
        answer(200, "creator_info"),
    ]

    post = publish_tiktok(engine, post_id, store)

    assert post.status == "published"
    form = dict(httpx.QueryParams(token.calls.last.request.content.decode()))
    assert form["client_key"] == CLIENT_KEY
    assert (form["grant_type"], "client_id" in form) == ("refresh_token", False)
    second = routes["creator"].calls[1].request
    assert second.headers["authorization"] == "Bearer act.cliplab-access-0002"
    saved = store.load(f"ref-{OPEN_ID}")
    assert saved is not None and saved.refresh_token == "rft.cliplab-refresh-0002"


def test_tiktok_is_registered_with_the_tiktok_app_settings() -> None:
    entry = registry.ENTRIES["tiktok"]
    assert entry.factory is tiktok.from_settings
    assert entry.settings_keys == ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET")
    assert recorded("video_init")["data"]["publish_id"] == PUBLISH_ID
