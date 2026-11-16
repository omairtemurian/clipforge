"""Tests for the Instagram publisher's refusals
(clipforge.publishers.instagram) through the publish run, against recorded
Meta Graph answers (respx): rate limits, 5xx answers, transient errors and
a used-up publishing limit are retried; policy refusals, missing
permissions, an expired sign-in, reels Instagram would not take and a
missing source-rights confirmation are final. Nothing reaches the
network."""

from typing import Any

import httpx
import pytest
import respx
from clipforge import posts
from clipforge.posts import PublishBlocked
from clipforge.publishers.meta_graph import TOKEN_URL
from clipforge.token_store import TokenStore
from instagram_publish_fakes import (
    answer,
    lengthen_clip,
    mock_reel,
    publish_instagram,
    ready_instagram_post,
)
from social_fakes import clip_of, set_rights
from sqlalchemy import Engine

FINISHED = [answer(200, "status_finished")]


@pytest.mark.parametrize(
    ("route", "answered", "status", "text"),
    [
        ("media", answer(429, "error_rate_limit"), "queued", "code 4"),
        ("media", answer(400, "error_rate_limit"), "queued", "request limit"),
        ("media", answer(500, "error_internal"), "queued", "HTTP 500"),
        ("media", httpx.Response(502, text="Bad Gateway"), "queued", "HTTP 502"),
        ("media", httpx.ConnectError("offline"), "queued", "Cannot reach"),
        ("media", answer(400, "error_daily_limit"), "queued", "maximum number"),
        ("media", answer(400, "error_restricted"), "failed", "is restricted"),
        ("media", answer(400, "error_spam"), "failed", "restrict certain"),
        ("media", answer(403, "error_permission"), "failed", "permission"),
        ("media", answer(400, "error_token_expired"), "failed", "connect the"),
        ("limit", answer(200, "publishing_limit_reached"), "queued", "100 Instagram"),
        ("rupload", answer(400, "rupload_failed"), "failed", "processing failed"),
        ("rupload", httpx.Response(503), "queued", "HTTP 503"),
        ("status", answer(200, "status_error_format"), "failed", "not supported"),
        ("status", answer(200, "status_error_timeout"), "queued", "too long"),
        ("status", answer(200, "status_expired"), "queued", "expired"),
        ("publish", answer(400, "error_spam"), "failed", "restrict certain"),
        ("publish", answer(500, "error_internal"), "queued", "HTTP 500"),
    ],
)
def test_refusals_are_retried_or_final(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    respx_mock: respx.MockRouter,
    route: str,
    answered: Any,
    status: str,
    text: str,
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store)
    effects: dict[str, Any] = {"status": FINISHED, route: answered}
    if route == "publish":
        effects["status"] = [answer(200, "status_finished")] * 2
    mock_reel(respx_mock, **effects)

    post = publish_instagram(engine, post_id, store)

    assert post.status == status
    assert post.error is not None and text.lower() in post.error.lower()


def test_a_used_up_limit_creates_no_container(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store)
    routes = mock_reel(respx_mock, limit=answer(200, "publishing_limit_reached"))

    post = publish_instagram(engine, post_id, store)

    assert post.status == "queued"
    assert not routes["media"].called


def test_an_unknown_limit_does_not_stop_the_reel(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store)
    mock_reel(respx_mock, limit=answer(500, "error_internal"), status=FINISHED)

    assert publish_instagram(engine, post_id, store).status == "published"


def test_an_expired_sign_in_that_cannot_be_exchanged_needs_a_reconnect(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store)
    respx_mock.get(TOKEN_URL).mock(return_value=answer(400, "error_token_expired"))
    routes = mock_reel(respx_mock, limit=answer(401, "error_token_expired"))

    post = publish_instagram(engine, post_id, store)

    assert post.status == "failed"
    assert post.error is not None and "Session has expired" in post.error
    assert not routes["media"].called


@pytest.mark.parametrize(
    ("payload", "seconds", "text"),
    [
        ({"caption": " ".join(f"#t{n}" for n in range(31))}, 30.0, "hashtags"),
        ({"collaborators": ["a", "b", "c", "d"]}, 30.0, "invalid"),
        ({"thumb_offset_ms": 30_000}, 30.0, "after the end"),
        ({}, 2.5, "3 s to 15 min"),
        ({}, 901.0, "3 s to 15 min"),
    ],
)
def test_reels_instagram_would_refuse_are_never_sent(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    respx_mock: respx.MockRouter,
    payload: dict[str, Any],
    seconds: float,
    text: str,
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store, payload)
    lengthen_clip(engine, clip_id, seconds)
    routes = mock_reel(respx_mock)

    post = publish_instagram(engine, post_id, store)

    assert post.status == "failed"
    assert post.error is not None and text in post.error
    assert not routes["media"].called


def test_publishing_needs_source_rights(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_instagram_post(engine, clip_id, store)
    set_rights(engine, clip_of(engine, clip_id).project_id, None)

    with pytest.raises(PublishBlocked) as blocked:
        publish_instagram(engine, post_id, store)

    assert blocked.value.code == "source_rights_missing"
    assert posts.get_post(engine, post_id).status == "queued"
    assert not respx_mock.calls
