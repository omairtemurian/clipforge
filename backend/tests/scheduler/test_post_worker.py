"""Tests for the posting worker (clipforge.scheduler.post_worker) on a fake
wall clock with a publisher of a made-up API (respx): due pickup, retries
with exponential backoff and a cap, the last attempt failing the post,
posts that cannot be published yet and uploads a stopped app left."""

import time
from datetime import timedelta

import respx
from clipforge import config, posts
from clipforge.scheduler import post_queue
from clipforge.scheduler.post_worker import PostWorker
from clipforge.scheduler.retry import RetryPolicy
from clipforge.token_store import TokenStore
from fake_clock import FakeWallClock
from post_worker_fakes import (
    RETRY,
    START,
    answer_busy,
    answer_published,
    connect,
    example,
    make_worker,
    queue,
)
from pytest import MonkeyPatch
from social_fakes import add_draft, clip_of, set_rights
from sqlalchemy import Engine


def test_worker_publishes_queued_posts_once_they_are_due(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
) -> None:
    route = answer_published(respx_mock)
    later = queue(engine, clip_id, connect(engine, store, "a"), START.replace(hour=10))
    now = queue(engine, clip_id, connect(engine, store, "b"))
    past = queue(engine, clip_id, connect(engine, store, "c"), START.replace(hour=8))
    draft = add_draft(engine, clip_id, connect(engine, store, "d"))
    worker = make_worker(engine, store, clock)

    assert worker.poll() == [now, past]
    assert worker.poll() == []
    clock.advance(minutes=59, seconds=59)
    assert worker.poll() == []
    clock.advance(seconds=1)
    assert worker.poll() == [later]

    assert route.call_count == 3
    published = posts.get_post(engine, later)
    assert (published.status, published.url, published.attempts) == (
        "published",
        "https://ex/v3",
        1,
    )
    assert published.attempted_at == START.replace(hour=10)
    assert posts.get_post(engine, draft).status == "draft"


def test_worker_retries_with_exponential_backoff_up_to_its_cap(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
) -> None:
    route = answer_busy(respx_mock)
    post_id = queue(engine, clip_id, connect(engine, store, "a"))
    worker = make_worker(engine, store, clock)
    waits = []

    for attempt in range(1, 5):
        assert worker.poll() == [post_id]
        post = posts.get_post(engine, post_id)
        assert (post.status, post.attempts) == ("queued", attempt)
        assert post.error == "ExampleTube is busy"
        assert post.next_attempt_at is not None
        wait = post.next_attempt_at - clock.now
        waits.append(wait.total_seconds())
        clock.advance(seconds=wait.total_seconds() - 1)
        assert worker.poll() == []
        clock.advance(seconds=1)

    assert waits == [60, 120, 240, 240]
    assert route.call_count == 4


def test_the_last_attempt_fails_the_post_with_its_error(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
) -> None:
    answer_busy(respx_mock)
    post_id = queue(engine, clip_id, connect(engine, store, "a"))
    retry = RetryPolicy(2, timedelta(seconds=60), timedelta(seconds=60))
    worker = make_worker(engine, store, clock, retry)

    worker.poll()
    clock.advance(minutes=1)
    worker.poll()

    post = posts.get_post(engine, post_id)
    assert (post.status, post.attempts, post.next_attempt_at) == ("failed", 2, None)
    assert post.error == "ExampleTube is busy (gave up after 2 attempts)"
    clock.advance(hours=1)
    assert worker.poll() == []


def test_queuing_a_failed_post_again_gives_it_fresh_attempts(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
) -> None:
    answer_busy(respx_mock)
    post_id = queue(engine, clip_id, connect(engine, store, "a"))
    retry = RetryPolicy(1, timedelta(seconds=60), timedelta(seconds=60))
    make_worker(engine, store, clock, retry).poll()
    assert posts.get_post(engine, post_id).status == "failed"

    post = posts.queue_post(engine, post_id)

    assert (post.status, post.attempts, post.error) == ("queued", 0, None)


def test_a_post_that_cannot_be_published_yet_waits_and_says_why(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
) -> None:
    route = answer_published(respx_mock)
    post_id = queue(engine, clip_id, connect(engine, store, "a"))
    set_rights(engine, clip_of(engine, clip_id).project_id, None)
    worker = make_worker(engine, store, clock)

    assert worker.poll() == []

    post = posts.get_post(engine, post_id)
    assert (post.status, post.attempts) == ("queued", 0)
    assert post.next_attempt_at == START + RETRY.cap
    assert post.error is not None and "source rights" in post.error
    set_rights(engine, clip_of(engine, clip_id).project_id, "own")
    clock.advance(seconds=RETRY.cap.total_seconds())
    assert worker.poll() == [post_id]
    assert posts.get_post(engine, post_id).status == "published"
    assert route.call_count == 1


def test_a_platform_without_its_app_keys_holds_the_post(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.settings, "tiktok_client_key", "")
    post_id = queue(engine, clip_id, connect(engine, store, "a"))
    worker = PostWorker(engine, store, retry=RETRY, now=clock)

    assert worker.poll() == []

    post = posts.get_post(engine, post_id)
    assert (post.status, post.next_attempt_at) == ("queued", START + RETRY.cap)
    assert post.error is not None and "TIKTOK_CLIENT_KEY" in post.error


def test_start_fails_the_uploads_a_stopped_app_left_unfinished(
    engine: Engine, store: TokenStore, clip_id: int, clock: FakeWallClock
) -> None:
    post_id = queue(engine, clip_id, connect(engine, store, "a"))
    posts.move(engine, post_id, "uploading", attempts=1)

    assert make_worker(engine, store, clock).recover() == [post_id]

    post = posts.get_post(engine, post_id)
    assert (post.status, post.error) == ("failed", post_queue.INTERRUPTED)


def test_the_worker_thread_publishes_with_the_ui_closed(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    monkeypatch: MonkeyPatch,
    respx_mock: respx.MockRouter,
) -> None:
    answer_published(respx_mock)
    monkeypatch.setattr(config.settings, "post_poll_s", 0.05)
    post_id = queue(engine, clip_id, connect(engine, store, "a"))
    worker = PostWorker(engine, store, retry=RETRY, publisher_for=example)

    worker.start()
    try:
        deadline = time.monotonic() + 10
        while posts.get_post(engine, post_id).status != "published":
            assert time.monotonic() < deadline, "the worker did not publish"
            time.sleep(0.05)
    finally:
        worker.stop(5.0)
