"""Tests for the Facebook publisher's reel post
(clipforge.publishers.facebook) through the publish run, against recorded
Meta Graph answers (respx): the Page access token found with the user's
token, the upload session, the resumable upload, the publish call with the
post's settings, the status polled with a fake sleep, collaborator
invitations, the permalink, upload retries and a 401 answered by a
long-lived token exchange (refusals: test_facebook_refusals.py). Nothing
reaches the network."""

import json

import httpx
import respx
from clipforge.models import Post
from clipforge.publishers import facebook, registry
from clipforge.publishers.base import clip_caption
from clipforge.publishers.facebook_api import PAGES_FIELDS
from clipforge.publishers.meta_graph import TOKEN_URL
from clipforge.token_store import TokenStore
from facebook_publish_fakes import (
    PAGE_ID,
    PAGE_TOKEN,
    PAGES_URL,
    VIDEO,
    answer,
    mock_reel,
    publish_facebook,
    ready_facebook_post,
)
from instagram_publish_fakes import ACCESS, APP_ID, APP_SECRET, VIDEO_SIZE
from social_fakes import clip_of
from sqlalchemy import Engine
from youtube_publish_fakes import write_sized_video

PAYLOAD = {
    "title": "The one habit",
    "description": "The one habit that changed everything #habits",
    "ai_generated": True,
    "collaborator_page_ids": ["104739358734099", " 104739358734098 "],
}
REEL_URL = "https://www.facebook.com/reel/1203457689012345/"


def assert_published(post: Post) -> None:
    assert (post.status, post.external_post_id, post.error) == (
        "published",
        VIDEO,
        None,
    )


def test_a_reel_is_uploaded_published_polled_and_shared(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store, PAYLOAD)
    data = write_sized_video(engine, clip_id, VIDEO_SIZE)
    routes = mock_reel(respx_mock)
    sleeps: list[float] = []

    post = publish_facebook(engine, post_id, store, sleeps=sleeps)

    assert_published(post)
    assert post.url == REEL_URL
    pages = routes["pages"].calls.last.request
    assert pages.headers["authorization"] == f"Bearer {ACCESS}"
    assert dict(pages.url.params) == {"fields": PAGES_FIELDS, "limit": "100"}
    start, finish = (c.request for c in routes["reels"].calls)
    assert json.loads(start.content) == {"upload_phase": "start"}
    assert start.headers["authorization"] == f"Bearer {PAGE_TOKEN}"
    assert json.loads(finish.content) == {
        "video_id": VIDEO,
        "upload_phase": "finish",
        "video_state": "PUBLISHED",
        "description": "The one habit that changed everything #habits",
        "title": "The one habit",
        "is_ai_generated": True,
    }
    sent = routes["rupload"].calls.last.request
    assert sent.headers["authorization"] == f"OAuth {PAGE_TOKEN}"
    assert (sent.headers["offset"], sent.headers["file_size"]) == (
        "0",
        str(VIDEO_SIZE),
    )
    assert sent.content == data
    assert routes["status"].call_count == 2
    assert sleeps == [facebook.STATUS_WAIT_S]
    invited = [c.request for c in routes["collaborators"].calls]
    assert [r.url.params["target_id"] for r in invited] == [
        "104739358734099",
        "104739358734098",
    ]
    assert invited[0].headers["authorization"] == f"Bearer {PAGE_TOKEN}"
    assert routes["permalink"].calls.last.request.headers["authorization"] == (
        f"Bearer {PAGE_TOKEN}"
    )


def test_the_default_description_is_the_title_and_hashtags(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store, {})
    routes = mock_reel(respx_mock, status=[answer(200, "status_published")])

    post = publish_facebook(engine, post_id, store)

    assert post.status == "published"
    finish = json.loads(routes["reels"].calls[1].request.content)
    assert finish == {
        "video_id": VIDEO,
        "upload_phase": "finish",
        "video_state": "PUBLISHED",
        "description": clip_caption(clip_of(engine, clip_id)),
    }
    assert not routes["collaborators"].called


def test_a_reel_still_processing_was_accepted_and_is_not_sent_again(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store)
    routes = mock_reel(respx_mock, status=lambda _r: answer(200, "status_processing"))
    sleeps: list[float] = []

    post = publish_facebook(engine, post_id, store, sleeps=sleeps)

    assert_published(post)
    assert routes["status"].call_count == facebook.STATUS_POLLS
    assert sleeps == [facebook.STATUS_WAIT_S] * (facebook.STATUS_POLLS - 1)
    assert routes["reels"].call_count == 2


def test_an_unreadable_status_does_not_fail_an_accepted_reel(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store)
    mock_reel(
        respx_mock,
        status=[answer(500, "error_internal"), answer(200, "status_published")],
    )

    assert_published(publish_facebook(engine, post_id, store))


def test_an_interrupted_upload_is_sent_again(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store)
    routes = mock_reel(
        respx_mock,
        rupload=[
            httpx.ReadError("connection reset"),
            answer(200, "rupload_retriable"),
            answer(200, "rupload_ok"),
        ],
        status=[answer(200, "status_published")],
    )
    sleeps: list[float] = []

    post = publish_facebook(engine, post_id, store, sleeps=sleeps)

    assert_published(post)
    assert routes["rupload"].call_count == 3
    assert sleeps == [2.0, 4.0]


def test_a_publish_without_answer_that_went_through_is_not_repeated(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store)
    routes = mock_reel(
        respx_mock,
        reels=[answer(200, "reel_start"), httpx.ReadTimeout("no answer")],
        status=[answer(200, "status_published")] * 2,
    )

    post = publish_facebook(engine, post_id, store)

    assert_published(post)
    assert routes["reels"].call_count == 2


def test_a_missing_permalink_does_not_fail_a_published_reel(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store)
    mock_reel(
        respx_mock,
        status=[answer(200, "status_published")],
        permalink=answer(500, "error_internal"),
    )

    post = publish_facebook(engine, post_id, store)

    assert_published(post)
    assert post.url is None


def test_a_refused_invitation_does_not_fail_a_published_reel(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store, PAYLOAD)
    routes = mock_reel(
        respx_mock,
        status=[answer(200, "status_published")],
        collaborators=answer(403, "error_permission"),
    )

    assert_published(publish_facebook(engine, post_id, store))
    assert routes["collaborators"].call_count == 2


def test_the_pages_of_a_user_with_many_are_read_page_by_page(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store)
    routes = mock_reel(
        respx_mock,
        pages=[answer(200, "pages_first_of_two"), answer(200, "pages_second_of_two")],
        status=[answer(200, "status_published")],
    )

    assert_published(publish_facebook(engine, post_id, store))
    first, second = (c.request for c in routes["pages"].calls)
    assert "after" not in first.url.params
    assert second.url.params["after"] == "QVFIUkxNEXT"
    assert routes["reels"].calls[0].request.headers["authorization"] == (
        f"Bearer {PAGE_TOKEN}"
    )


def test_a_401_exchanges_the_token_for_a_new_long_lived_one(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store)
    token = respx_mock.get(TOKEN_URL).mock(return_value=answer(200, "token_refreshed"))
    routes = mock_reel(
        respx_mock,
        pages=[answer(401, "error_token_expired"), answer(200, "pages")],
        status=[answer(200, "status_published")],
    )

    post = publish_facebook(engine, post_id, store)

    assert_published(post)
    assert dict(token.calls.last.request.url.params) == {
        "grant_type": "fb_exchange_token",
        "fb_exchange_token": ACCESS,
        "client_id": APP_ID,
        "client_secret": APP_SECRET,
    }
    second = routes["pages"].calls[1].request
    assert second.headers["authorization"] == "Bearer EAAcliplab-long-0002"
    saved = store.load(f"ref-{PAGE_ID}")
    assert saved is not None and saved.access_token == "EAAcliplab-long-0002"
    assert PAGES_URL in str(second.url)


def test_facebook_is_registered_with_the_meta_app_settings() -> None:
    entry = registry.ENTRIES["facebook"]
    assert entry.factory is facebook.from_settings
    assert entry.settings_keys == ("META_APP_ID", "META_APP_SECRET")
