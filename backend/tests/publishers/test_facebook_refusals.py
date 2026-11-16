"""Tests for the Facebook publisher's refusals
(clipforge.publishers.facebook) through the publish run, against recorded
Meta Graph answers (respx): rate limits, 5xx answers, temporary blocks and
transient errors are retried; policy refusals, missing permissions, an
expired sign-in, a Page the user cannot post to any more, reels Facebook
would not take and a missing source-rights confirmation are final. Nothing
reaches the network."""

from typing import Any

import httpx
import pytest
import respx
from clipforge import posts
from clipforge.posts import PublishBlocked
from clipforge.publishers.meta_graph import TOKEN_URL
from clipforge.token_store import TokenStore
from facebook_publish_fakes import (
    answer,
    lengthen_clip,
    mock_reel,
    publish_facebook,
    ready_facebook_post,
)
from social_fakes import clip_of, set_rights
from sqlalchemy import Engine

START = answer(200, "reel_start")
PUBLISHED = [answer(200, "status_published")]


@pytest.mark.parametrize(
    ("effects", "status", "text"),
    [
        ({"reels": [answer(429, "error_rate_limit")]}, "queued", "code 4"),
        ({"reels": [answer(400, "error_rate_limit")]}, "queued", "request limit"),
        ({"reels": [answer(500, "error_internal")]}, "queued", "HTTP 500"),
        ({"reels": [httpx.Response(502, text="Bad")]}, "queued", "HTTP 502"),
        ({"reels": [httpx.ConnectError("offline")]}, "queued", "Cannot reach"),
        ({"reels": [answer(400, "error_abusive")]}, "queued", "temporarily blocked"),
        ({"reels": [answer(400, "error_duration")]}, "failed", "3 and 90 seconds"),
        ({"reels": [answer(403, "error_permission")]}, "failed", "permission"),
        ({"reels": [answer(400, "error_token_expired")]}, "failed", "connect the"),
        (
            {"reels": [httpx.Response(200, json={"video_id": 1})]},
            "queued",
            "did not start",
        ),
        ({"pages": answer(500, "error_internal")}, "queued", "HTTP 500"),
        ({"pages": answer(403, "error_permission")}, "failed", "permission"),
        ({"rupload": answer(400, "rupload_failed")}, "failed", "processing failed"),
        ({"rupload": httpx.Response(503)}, "queued", "HTTP 503"),
        (
            {"reels": [START, answer(400, "error_duration")]},
            "failed",
            "between 3 and 90 seconds",
        ),
        (
            {
                "reels": [START, answer(500, "error_internal")],
                "status": answer(200, "status_processing"),
            },
            "queued",
            "HTTP 500",
        ),
        (
            {"status": answer(200, "status_processing_error")},
            "failed",
            "Resolution too low",
        ),
        ({"status": answer(200, "status_expired")}, "queued", "video status expired"),
    ],
)
def test_refusals_are_retried_or_final(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    respx_mock: respx.MockRouter,
    effects: dict[str, Any],
    status: str,
    text: str,
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store)
    mock_reel(respx_mock, **{"status": PUBLISHED, **effects})

    post = publish_facebook(engine, post_id, store)

    assert post.status == status
    assert post.error is not None and text.lower() in post.error.lower()


def test_a_page_the_user_cannot_post_to_any_more_gets_no_reel(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store)
    routes = mock_reel(respx_mock, pages=answer(200, "pages_stats_only"))

    post = publish_facebook(engine, post_id, store)

    assert post.status == "failed"
    assert not routes["reels"].called and not routes["rupload"].called


def test_an_expired_sign_in_that_cannot_be_exchanged_needs_a_reconnect(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store)
    respx_mock.get(TOKEN_URL).mock(return_value=answer(400, "error_token_expired"))
    routes = mock_reel(respx_mock, pages=answer(401, "error_token_expired"))

    post = publish_facebook(engine, post_id, store)

    assert post.status == "failed"
    assert post.error is not None and "Session has expired" in post.error
    assert not routes["reels"].called


@pytest.mark.parametrize(
    ("payload", "seconds", "text"),
    [
        ({"collaborator_page_ids": ["not-an-id"]}, 30.0, "invalid"),
        ({"collaborator_page_ids": ["1234567"] * 11}, 30.0, "invalid"),
        ({}, 2.5, "3 to 90 s"),
        ({}, 91.0, "3 to 90 s"),
    ],
)
def test_reels_facebook_would_refuse_are_never_sent(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    respx_mock: respx.MockRouter,
    payload: dict[str, Any],
    seconds: float,
    text: str,
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store, payload)
    lengthen_clip(engine, clip_id, seconds)
    routes = mock_reel(respx_mock)

    post = publish_facebook(engine, post_id, store)

    assert post.status == "failed"
    assert post.error is not None and text in post.error
    assert not routes["pages"].called and not routes["reels"].called


def test_publishing_needs_source_rights(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_facebook_post(engine, clip_id, store)
    set_rights(engine, clip_of(engine, clip_id).project_id, None)

    with pytest.raises(PublishBlocked) as blocked:
        publish_facebook(engine, post_id, store)

    assert blocked.value.code == "source_rights_missing"
    assert posts.get_post(engine, post_id).status == "queued"
    assert not respx_mock.calls
