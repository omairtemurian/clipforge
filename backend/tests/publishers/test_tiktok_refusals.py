"""Tests for the TikTok publisher's refusals (clipforge.publishers.tiktok)
through the publish run, against recorded TikTok answers (respx): rate
limits, 5xx answers and expired upload links are retried; policy refusals,
posts against the creator's rules and a missing source-rights confirmation
are final. Nothing reaches the network."""

from typing import Any

import httpx
import pytest
import respx
from clipforge import posts
from clipforge.posts import PublishBlocked
from clipforge.publishers import tiktok
from clipforge.token_store import TokenStore
from social_fakes import clip_of, set_rights
from sqlalchemy import Engine
from tiktok_publish_fakes import (
    answer,
    mock_direct_post,
    publish_tiktok,
    ready_tiktok_post,
)


@pytest.mark.parametrize(
    ("route", "answered", "status", "text"),
    [
        ("init", answer(429, "error_rate_limit"), "queued", "rate_limit_exceeded"),
        ("init", answer(500, "error_internal"), "queued", "HTTP 500"),
        ("init", httpx.Response(502, text="Bad Gateway"), "queued", "HTTP 502"),
        ("creator", answer(200, "creator_info_post_cap"), "queued", "daily post cap"),
        ("init", answer(403, "error_unaudited"), "failed", "unaudited TikTok app"),
        ("creator", answer(200, "creator_info_banned"), "failed", "banned"),
        ("init", answer(401, "error_scope_not_authorized"), "failed", "video.publish"),
        ("put", httpx.Response(403), "queued", "upload link expired"),
        ("put", httpx.Response(400), "failed", "refused the video file"),
        ("status", answer(200, "status_failed_spam"), "failed", "spam_risk_text"),
        ("status", answer(200, "status_failed_internal"), "queued", "internal"),
    ],
)
def test_refusals_are_retried_or_final(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    respx_mock: respx.MockRouter,
    route: str,
    answered: httpx.Response,
    status: str,
    text: str,
) -> None:
    post_id = ready_tiktok_post(engine, clip_id, store)
    respx_mock.post(tiktok.TOKEN_URL).mock(return_value=answer(200, "token_refreshed"))
    routes = mock_direct_post(respx_mock)
    routes[route].side_effect = None
    routes[route].return_value = answered

    post = publish_tiktok(engine, post_id, store)

    assert post.status == status
    assert post.error is not None and text in post.error


@pytest.mark.parametrize(
    ("creator", "payload", "text"),
    [
        ("creator_info", {"caption": "x"}, "privacy level"),
        (
            "creator_info",
            {"privacy_level": "SELF_ONLY", "branded_content": True},
            "invalid",
        ),
        (
            "creator_info_private",
            {"privacy_level": "PUBLIC_TO_EVERYONE"},
            "cannot post as PUBLIC_TO_EVERYONE",
        ),
        ("creator_info_private", {"privacy_level": "SELF_ONLY"}, "at most 2 s"),
    ],
)
def test_posts_against_the_creator_rules_are_never_sent(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    respx_mock: respx.MockRouter,
    creator: str,
    payload: dict[str, Any],
    text: str,
) -> None:
    post_id = ready_tiktok_post(engine, clip_id, store, payload)
    routes = mock_direct_post(respx_mock, creator=answer(200, creator))

    post = publish_tiktok(engine, post_id, store)

    assert post.status == "failed"
    assert post.error is not None and text in post.error
    assert not routes["init"].called


def test_publishing_needs_source_rights(
    engine: Engine, clip_id: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    post_id = ready_tiktok_post(engine, clip_id, store)
    set_rights(engine, clip_of(engine, clip_id).project_id, None)

    with pytest.raises(PublishBlocked) as blocked:
        publish_tiktok(engine, post_id, store)

    assert blocked.value.code == "source_rights_missing"
    assert posts.get_post(engine, post_id).status == "queued"
    assert not respx_mock.calls
