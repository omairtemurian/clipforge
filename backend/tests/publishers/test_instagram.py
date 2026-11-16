"""Tests for the Instagram publisher's reel post
(clipforge.publishers.instagram) through the publish run, against recorded
Meta Graph answers (respx): the publishing limit check, the container
with its post settings, the resumable upload, the container status polled
with a fake sleep, media_publish and the permalink, upload retries and a
401 answered by a long-lived token exchange (refusals:
test_instagram_refusals.py). Nothing reaches the network."""

import json

import httpx
import respx
from clipforge.publishers import instagram, registry
from clipforge.publishers.meta_graph import TOKEN_URL
from clipforge.token_store import TokenStore
from instagram_publish_fakes import (
    ACCESS,
    APP_ID,
    APP_SECRET,
    CONTAINER,
    IG_USER,
    MEDIA,
    VIDEO_SIZE,
    answer,
    mock_reel,
    publish_instagram,
    ready_instagram_post,
)
from sqlalchemy import Engine
from youtube_publish_fakes import write_sized_video

PAYLOAD = {
    "caption": "The one habit that changed everything #habits",
    "share_to_feed": False,
    "collaborators": ["@friend.one", "friend_two"],
    "thumb_offset_ms": 1500,
    "audio_name": "Clip Lab original",
    "ai_generated": True,
    "trial_strategy": "SS_PERFORMANCE",
}


def test_a_reel_is_created_uploaded_polled_and_published(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store, PAYLOAD)
    data = write_sized_video(engine, clip_id, VIDEO_SIZE)
    routes = mock_reel(respx_mock)
    sleeps: list[float] = []

    post = publish_instagram(engine, post_id, store, sleeps=sleeps)

    assert (post.status, post.external_post_id, post.error) == (
        "published",
        MEDIA,
        None,
    )
    assert post.url == "https://www.instagram.com/reel/DCliPLab01x/"
    limit = routes["limit"].calls.last.request
    assert limit.headers["authorization"] == f"Bearer {ACCESS}"
    assert limit.url.params["fields"] == "config,quota_usage"
    assert json.loads(routes["media"].calls.last.request.content) == {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": "The one habit that changed everything #habits",
        "share_to_feed": False,
        "collaborators": ["friend.one", "friend_two"],
        "thumb_offset": 1500,
        "audio_name": "Clip Lab original",
        "is_ai_generated": True,
        "trial_params": {"graduation_strategy": "SS_PERFORMANCE"},
    }
    sent = routes["rupload"].calls.last.request
    assert sent.headers["authorization"] == f"OAuth {ACCESS}"
    assert (sent.headers["offset"], sent.headers["file_size"]) == (
        "0",
        str(VIDEO_SIZE),
    )
    assert sent.headers["content-length"] == str(VIDEO_SIZE)
    assert sent.content == data
    assert routes["status"].call_count == 2
    assert routes["status"].calls.last.request.url.params["fields"] == (
        "status_code,status"
    )
    assert sleeps == [instagram.STATUS_WAIT_S] * 2
    assert json.loads(routes["publish"].calls.last.request.content) == {
        "creation_id": CONTAINER
    }


def test_the_default_caption_is_the_title_and_hashtags(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store, {})
    routes = mock_reel(respx_mock, status=[answer(200, "status_finished")])

    post = publish_instagram(engine, post_id, store)

    assert post.status == "published"
    body = json.loads(routes["media"].calls.last.request.content)
    assert body == {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": body["caption"],
        "share_to_feed": True,
    }


def test_a_reel_still_processing_is_tried_again_later(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store)
    routes = mock_reel(respx_mock, status=lambda _r: answer(200, "status_in_progress"))
    sleeps: list[float] = []

    post = publish_instagram(engine, post_id, store, sleeps=sleeps)

    assert post.status == "queued"
    assert post.error is not None and "still processing" in post.error
    assert routes["status"].call_count == instagram.STATUS_POLLS
    assert sleeps == [instagram.STATUS_WAIT_S] * instagram.STATUS_POLLS
    assert not routes["publish"].called


def test_an_interrupted_upload_is_sent_again(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store)
    routes = mock_reel(
        respx_mock,
        rupload=[
            httpx.ReadError("connection reset"),
            answer(200, "rupload_retriable"),
            answer(200, "rupload_ok"),
        ],
        status=[answer(200, "status_finished")],
    )
    sleeps: list[float] = []

    post = publish_instagram(engine, post_id, store, sleeps=sleeps)

    assert post.status == "published"
    assert routes["rupload"].call_count == 3
    assert sleeps[:2] == [2.0, 4.0]


def test_a_publish_without_answer_that_went_through_is_kept(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store)
    mock_reel(
        respx_mock,
        status=[answer(200, "status_finished"), answer(200, "status_published")],
        publish=httpx.ReadTimeout("no answer"),
    )

    post = publish_instagram(engine, post_id, store)

    assert (post.status, post.external_post_id, post.url) == (
        "published",
        CONTAINER,
        None,
    )


def test_a_missing_permalink_does_not_fail_a_published_reel(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store)
    mock_reel(
        respx_mock,
        status=[answer(200, "status_finished")],
        permalink=answer(500, "error_internal"),
    )

    post = publish_instagram(engine, post_id, store)

    assert (post.status, post.external_post_id, post.url) == ("published", MEDIA, None)


def test_a_401_exchanges_the_token_for_a_new_long_lived_one(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store)
    token = respx_mock.get(TOKEN_URL).mock(return_value=answer(200, "token_refreshed"))
    routes = mock_reel(
        respx_mock,
        limit=[answer(401, "error_token_expired"), answer(200, "publishing_limit")],
        status=[answer(200, "status_finished")],
    )

    post = publish_instagram(engine, post_id, store)

    assert post.status == "published"
    assert dict(token.calls.last.request.url.params) == {
        "grant_type": "fb_exchange_token",
        "fb_exchange_token": ACCESS,
        "client_id": APP_ID,
        "client_secret": APP_SECRET,
    }
    second = routes["limit"].calls[1].request
    assert second.headers["authorization"] == "Bearer EAAcliplab-long-0002"
    assert routes["rupload"].calls.last.request.headers["authorization"] == (
        "OAuth EAAcliplab-long-0002"
    )
    saved = store.load(f"ref-{IG_USER}")
    assert saved is not None and saved.access_token == "EAAcliplab-long-0002"


def test_instagram_is_registered_with_the_meta_app_settings() -> None:
    entry = registry.ENTRIES["instagram"]
    assert entry.factory is instagram.from_settings
    assert entry.settings_keys == ("META_APP_ID", "META_APP_SECRET")
