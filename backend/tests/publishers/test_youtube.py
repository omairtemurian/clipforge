"""Tests for the YouTube publisher's upload (clipforge.publishers.youtube)
through the publish run, against recorded YouTube answers (respx): the
resumable upload in chunks with its metadata, resuming after an interrupted
chunk, a 401 token refresh, rate limits, quota and 5xx answers (retryable),
policy rejections (final) and the source-rights guard. Nothing reaches the
network."""

from typing import Any

import httpx
import pytest
import respx
from clipforge import posts
from clipforge.models import Post
from clipforge.posts import PublishBlocked
from clipforge.publishers import youtube
from clipforge.publishers.publish import publish_post
from clipforge.publishers.youtube_upload import MAX_RESUMES, UPLOAD_URL
from clipforge.sources.gdrive import TOKEN_URL
from clipforge.token_store import TokenStore
from social_fakes import clip_of, set_rights
from sqlalchemy import Engine
from youtube_publish_fakes import (
    ACCESS,
    CHANNEL_ID,
    SESSION_URL,
    VIDEO_ID,
    VIDEO_SIZE,
    answer,
    make_publisher,
    queue_youtube_post,
    received,
    session_started,
    units_used,
    write_sized_video,
)

PAYLOAD = {
    "title": "The one habit <that> changed everything",
    "description": "From the full talk.",
    "tags": ["#habits", "productivity", "habits"],
    "category_id": "27",
    "privacy": "public",
    "made_for_kids": False,
    "synthetic_media": True,
    "notify_subscribers": False,
}


def run(engine: Engine, post_id: int, store: TokenStore, **kwargs: Any) -> Post:
    """Publish the post with a test YouTubePublisher."""
    publisher = make_publisher(**kwargs)
    return publish_post(engine, post_id, store, lambda _platform: publisher)


def ranges(route: respx.Route) -> list[str]:
    """Return the Content-Range of each request the route got."""
    return [call.request.headers["content-range"] for call in route.calls]


def test_upload_sends_metadata_then_the_file_in_chunks(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    data = write_sized_video(engine, clip_id)
    post_id = queue_youtube_post(engine, clip_id, store, PAYLOAD)
    start = respx_mock.post(UPLOAD_URL).mock(return_value=session_started())
    put = respx_mock.put(SESSION_URL).mock(
        side_effect=[
            received(262_143),
            received(524_287),
            answer(201, "video_uploaded"),
        ]
    )

    post = run(engine, post_id, store)

    assert (post.status, post.external_post_id, post.error) == (
        "published",
        VIDEO_ID,
        None,
    )
    assert post.url == f"https://www.youtube.com/watch?v={VIDEO_ID}"
    request = start.calls.last.request
    assert dict(request.url.params) == {
        "uploadType": "resumable",
        "part": "snippet,status",
        "notifySubscribers": "false",
    }
    assert request.headers["authorization"] == f"Bearer {ACCESS}"
    assert request.headers["x-upload-content-length"] == str(VIDEO_SIZE)
    assert request.headers["x-upload-content-type"] == "video/mp4"
    assert httpx.Response(200, content=request.content).json() == {
        "snippet": {
            "title": "The one habit that changed everything",
            "description": "From the full talk.",
            "categoryId": "27",
            "tags": ["habits", "productivity"],
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }
    assert ranges(put) == [
        f"bytes 0-262143/{VIDEO_SIZE}",
        f"bytes 262144-524287/{VIDEO_SIZE}",
        f"bytes 524288-{VIDEO_SIZE - 1}/{VIDEO_SIZE}",
    ]
    assert b"".join(call.request.content for call in put.calls) == data
    assert units_used(engine, "youtube_uploads") == 1


def test_upload_resumes_after_an_interrupted_chunk(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    write_sized_video(engine, clip_id)
    post_id = queue_youtube_post(engine, clip_id, store)
    respx_mock.post(UPLOAD_URL).mock(return_value=session_started())
    put = respx_mock.put(SESSION_URL).mock(
        side_effect=[
            received(262_143),
            httpx.ReadError("connection reset"),
            received(393_215),
            answer(503, "error_backend"),
            received(524_287),
            answer(201, "video_uploaded"),
        ]
    )
    sleeps: list[float] = []

    post = run(engine, post_id, store, sleeps=sleeps)

    assert post.status == "published"
    assert ranges(put) == [
        f"bytes 0-262143/{VIDEO_SIZE}",
        f"bytes 262144-524287/{VIDEO_SIZE}",
        f"bytes */{VIDEO_SIZE}",
        f"bytes 393216-{VIDEO_SIZE - 1}/{VIDEO_SIZE}",
        f"bytes */{VIDEO_SIZE}",
        f"bytes 524288-{VIDEO_SIZE - 1}/{VIDEO_SIZE}",
    ]
    assert put.calls[2].request.content == b""
    assert sleeps == [2.0, 4.0]


def test_status_check_can_find_the_upload_already_complete(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    write_sized_video(engine, clip_id, 1000)
    post_id = queue_youtube_post(engine, clip_id, store)
    respx_mock.post(UPLOAD_URL).mock(return_value=session_started())
    respx_mock.put(SESSION_URL).mock(
        side_effect=[httpx.ReadTimeout("slow"), answer(200, "video_uploaded")]
    )

    assert run(engine, post_id, store).external_post_id == VIDEO_ID


def test_an_upload_interrupted_too_often_is_retried_later(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    write_sized_video(engine, clip_id, 1000)
    post_id = queue_youtube_post(engine, clip_id, store)
    respx_mock.post(UPLOAD_URL).mock(return_value=session_started())
    respx_mock.put(SESSION_URL).mock(side_effect=httpx.ConnectError("offline"))
    sleeps: list[float] = []

    post = run(engine, post_id, store, sleeps=sleeps)

    assert post.status == "queued"
    assert post.error is not None and "interrupted" in post.error
    assert sleeps == [float(2**n) for n in range(1, MAX_RESUMES + 1)]


def test_an_expired_upload_session_is_retried_later(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    write_sized_video(engine, clip_id, 1000)
    post_id = queue_youtube_post(engine, clip_id, store)
    respx_mock.post(UPLOAD_URL).mock(return_value=session_started())
    respx_mock.put(SESSION_URL).mock(return_value=httpx.Response(404))

    post = run(engine, post_id, store)

    assert (post.status, post.error) == (
        "queued",
        "The YouTube upload session expired.",
    )


def test_a_401_refreshes_the_token_once(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    write_sized_video(engine, clip_id, 1000)
    post_id = queue_youtube_post(engine, clip_id, store)
    token = respx_mock.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "ya29.new", "expires_in": 3599}
        )
    )
    start = respx_mock.post(UPLOAD_URL).mock(
        side_effect=[answer(401, "error_unauthorized"), session_started()]
    )
    respx_mock.put(SESSION_URL).mock(return_value=answer(201, "video_uploaded"))

    post = run(engine, post_id, store)

    assert post.status == "published"
    assert token.call_count == 1
    assert start.calls[1].request.headers["authorization"] == "Bearer ya29.new"
    saved = store.load(f"ref-{CHANNEL_ID}")
    assert saved is not None and saved.access_token == "ya29.new"


@pytest.mark.parametrize(
    ("answered", "status", "text"),
    [
        (answer(429, "error_rate_limit"), "queued", "rateLimitExceeded"),
        (answer(403, "error_quota"), "queued", "quotaExceeded"),
        (answer(503, "error_backend"), "queued", "HTTP 503"),
        (answer(403, "error_forbidden_privacy"), "failed", "forbiddenPrivacySetting"),
        (answer(401, "error_unauthorized"), "failed", "connect the account again"),
    ],
)
def test_refusals_are_retried_or_final(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    respx_mock: respx.MockRouter,
    answered: httpx.Response,
    status: str,
    text: str,
) -> None:
    write_sized_video(engine, clip_id, 1000)
    post_id = queue_youtube_post(engine, clip_id, store)
    respx_mock.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "ya29.new"})
    )
    respx_mock.post(UPLOAD_URL).mock(return_value=answered)

    post = run(engine, post_id, store)

    assert post.status == status
    assert post.error is not None and text in post.error


def test_a_video_rejected_by_policy_fails_the_post(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    write_sized_video(engine, clip_id, 1000)
    post_id = queue_youtube_post(engine, clip_id, store)
    respx_mock.post(UPLOAD_URL).mock(return_value=session_started())
    respx_mock.put(SESSION_URL).mock(return_value=answer(201, "video_rejected"))

    post = run(engine, post_id, store)

    assert (post.status, post.error) == (
        "failed",
        "YouTube rejected the video (duplicate).",
    )


def test_publishing_needs_source_rights(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = queue_youtube_post(engine, clip_id, store)
    set_rights(engine, clip_of(engine, clip_id).project_id, None)

    with pytest.raises(PublishBlocked) as blocked:
        run(engine, post_id, store)

    assert blocked.value.code == "source_rights_missing"
    assert posts.get_post(engine, post_id).status == "queued"
    assert not respx_mock.calls


def test_youtube_is_registered_with_the_google_app_settings() -> None:
    from clipforge.publishers import registry

    entry = registry.ENTRIES["youtube"]
    assert entry.factory is youtube.from_settings
    assert entry.settings_keys == (
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
    )
