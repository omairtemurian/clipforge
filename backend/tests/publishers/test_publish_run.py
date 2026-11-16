"""Tests for the publish run (clipforge.publishers.publish) with a publisher
of a made-up API (respx): success, retryable and final failures, a lost
sign-in and the guards that keep a post queued."""

from pathlib import Path

import httpx
import pytest
import respx
from clipforge import posts
from clipforge.models import PostStatus
from clipforge.oauth_tokens import Token
from clipforge.posts import IllegalTransition, PublishBlocked
from clipforge.publishers.publish import publish_post
from clipforge.token_store import TokenStore
from social_fakes import (
    ACCESS,
    CLIENT,
    VIDEOS_URL,
    ExamplePublisher,
    add_draft,
    clip_of,
    set_rights,
)
from sqlalchemy import Engine


@pytest.fixture
def queued(engine: Engine, clip_id: int, store: TokenStore) -> int:
    """A queued post of clip_id to a connected account."""
    post_id = add_draft(engine, clip_id)
    store.save("ref-acct-1", Token(access_token=ACCESS))
    return posts.queue_post(engine, post_id).id


def publisher_for(_platform: str) -> ExamplePublisher:
    return ExamplePublisher(CLIENT)


def test_publish_run_uploads_and_records_the_live_post(
    engine: Engine, queued: int, store: TokenStore, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.post(VIDEOS_URL).mock(
        return_value=httpx.Response(201, json={"id": "v9", "link": "https://ex/v9"})
    )

    post = publish_post(engine, queued, store, publisher_for)

    assert (post.status, post.external_post_id, post.url) == (
        "published",
        "v9",
        "https://ex/v9",
    )
    assert (post.attempts, post.error) == (1, None)
    request = route.calls.last.request
    assert request.url.params["title"] == "Bit"
    assert request.headers["authorization"] == f"Bearer {ACCESS}"


@pytest.mark.parametrize(
    ("answer", "status"),
    [(httpx.Response(503), "queued"), (httpx.Response(400, text="bad"), "failed")],
)
def test_publish_run_retries_passing_failures_and_fails_the_others(
    engine: Engine,
    queued: int,
    store: TokenStore,
    respx_mock: respx.MockRouter,
    answer: httpx.Response,
    status: PostStatus,
) -> None:
    respx_mock.post(VIDEOS_URL).mock(return_value=answer)

    post = publish_post(engine, queued, store, publisher_for)

    assert (post.status, post.attempts) == (status, 1)
    assert post.error is not None and "ExampleTube" in post.error


def test_publish_run_fails_a_post_whose_sign_in_is_gone(
    engine: Engine, queued: int, store: TokenStore
) -> None:
    store.delete("ref-acct-1")
    post = publish_post(engine, queued, store, publisher_for)
    assert post.status == "failed"
    assert post.error == "ExampleTube is not connected."


def test_publish_run_is_blocked_without_source_rights(
    engine: Engine, clip_id: int, queued: int, store: TokenStore
) -> None:
    set_rights(engine, clip_of(engine, clip_id).project_id, None)

    with pytest.raises(PublishBlocked) as blocked:
        publish_post(engine, queued, store, publisher_for)

    assert blocked.value.code == "source_rights_missing"
    post = posts.get_post(engine, queued)
    assert (post.status, post.attempts) == ("queued", 0)


def test_publish_run_needs_a_rendered_clip_and_a_queued_post(
    engine: Engine, clip_id: int, queued: int, store: TokenStore
) -> None:
    video = clip_of(engine, clip_id).output_path
    assert video is not None
    Path(video).unlink()
    with pytest.raises(PublishBlocked) as blocked:
        publish_post(engine, queued, store, publisher_for)
    assert blocked.value.code == "clip_not_rendered"

    posts.move(engine, queued, "canceled")
    with pytest.raises(IllegalTransition):
        publish_post(engine, queued, store, publisher_for)
