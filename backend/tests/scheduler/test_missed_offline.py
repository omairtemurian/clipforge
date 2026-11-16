"""Tests for the posts missed while the app was off (SPEC-v2 3.10): on a
fake wall clock, a start after downtime posts them late or skips them per
the post_missed_policy setting; posts a running worker already saw, posts
in the grace window and future posts are left to the polls."""

from datetime import timedelta

import pytest
import respx
from clipforge import config, posts
from clipforge.scheduler import post_queue
from clipforge.scheduler.post_worker import PostWorker
from clipforge.token_store import TokenStore
from fake_clock import FakeWallClock
from post_worker_fakes import (
    RETRY,
    START,
    answer_published,
    connect,
    example,
    make_worker,
    queue,
)
from pytest import MonkeyPatch
from sqlalchemy import Engine


def downtime_posts(engine: Engine, store: TokenStore, clip_id: int) -> dict[str, int]:
    """Queue posts (one account each, so rate limits stay out of the way)
    around a start at START after a downtime of several hours: two due
    while the app was off, one due a minute before the start (grace), one
    held back by the running worker before it stopped, one waiting for a
    retry and one in the future. Their ids by name."""
    names = {
        "three_hours": START - timedelta(hours=3),
        "one_hour": START - timedelta(hours=1),
        "in_grace": START - timedelta(minutes=1),
        "held": START - timedelta(hours=2),
        "retry": START - timedelta(hours=4),
        "future": START + timedelta(hours=1),
    }
    ids = {
        name: queue(engine, clip_id, connect(engine, store, name), at)
        for name, at in names.items()
    }
    post_queue.defer(engine, ids["held"], START - timedelta(minutes=30), "limit")
    posts.move(engine, ids["retry"], "uploading", attempts=1)
    posts.move(
        engine,
        ids["retry"],
        "queued",
        next_attempt_at=START - timedelta(hours=3),
        error="ExampleTube is busy",
    )
    return ids


@pytest.fixture
def ids(engine: Engine, store: TokenStore, clip_id: int) -> dict[str, int]:
    return downtime_posts(engine, store, clip_id)


def test_missed_posts_are_the_never_tried_ones_due_before_the_grace(
    engine: Engine, ids: dict[str, int]
) -> None:
    missed = post_queue.missed_posts(engine, START - timedelta(minutes=10))

    assert [post.id for post in missed] == [ids["three_hours"], ids["one_hour"]]


def test_post_late_publishes_the_missed_posts_on_the_first_poll(
    engine: Engine,
    store: TokenStore,
    ids: dict[str, int],
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
) -> None:
    route = answer_published(respx_mock)
    assert config.settings.post_missed_policy == "post_late"
    worker = make_worker(engine, store, clock)

    assert worker.recover() == []
    assert worker.catch_up() == []
    ran = worker.poll()

    due = ["three_hours", "one_hour", "in_grace", "held", "retry"]
    assert sorted(ran) == sorted(ids[name] for name in due)
    for name in due:
        post = posts.get_post(engine, ids[name])
        assert (post.status, post.error) == ("published", None), name
        assert post.url is not None and post.url.startswith("https://ex/v")
    assert posts.get_post(engine, ids["future"]).status == "queued"
    assert route.call_count == len(due)


def test_skip_marks_the_missed_posts_skipped_and_posts_the_others(
    engine: Engine,
    store: TokenStore,
    ids: dict[str, int],
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
    monkeypatch: MonkeyPatch,
) -> None:
    route = answer_published(respx_mock)
    monkeypatch.setattr(config.settings, "post_missed_policy", "skip")
    worker = make_worker(engine, store, clock)

    assert worker.catch_up() == [ids["three_hours"], ids["one_hour"]]
    ran = worker.poll()

    for name in ("three_hours", "one_hour"):
        post = posts.get_post(engine, ids[name])
        assert (post.status, post.error) == ("skipped", post_queue.SKIPPED)
        assert (post.attempts, post.attempted_at, post.url) == (0, None, None)
    published = ["in_grace", "held", "retry"]
    assert sorted(ran) == sorted(ids[name] for name in published)
    assert route.call_count == len(published)
    clock.advance(hours=2)
    assert worker.poll() == [ids["future"]]
    assert worker.catch_up() == []


def test_the_grace_setting_decides_what_counts_as_missed(
    engine: Engine,
    store: TokenStore,
    ids: dict[str, int],
    clock: FakeWallClock,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.settings, "post_missed_policy", "skip")
    monkeypatch.setattr(config.settings, "post_missed_grace_s", 0.0)

    skipped = make_worker(engine, store, clock).catch_up()

    assert skipped == [ids["three_hours"], ids["one_hour"], ids["in_grace"]]


def test_start_applies_the_policy_before_the_first_poll(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
    monkeypatch: MonkeyPatch,
) -> None:
    route = answer_published(respx_mock)
    monkeypatch.setattr(config.settings, "post_missed_policy", "skip")
    post_id = queue(engine, clip_id, connect(engine, store, "a"), START.replace(hour=7))
    worker = PostWorker(
        engine, store, interval=0.05, retry=RETRY, publisher_for=example, now=clock
    )

    worker.start()
    worker.stop(5)

    assert posts.get_post(engine, post_id).status == "skipped"
    assert route.call_count == 0


def test_a_skipped_post_can_be_queued_again_or_canceled(
    engine: Engine,
    store: TokenStore,
    ids: dict[str, int],
    clock: FakeWallClock,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.settings, "post_missed_policy", "skip")
    make_worker(engine, store, clock).catch_up()

    again = posts.queue_post(engine, ids["three_hours"], START + timedelta(hours=2))
    canceled = posts.move(engine, ids["one_hour"], "canceled")

    assert (again.status, again.error, again.attempts) == ("queued", None, 0)
    assert canceled.status == "canceled"
    with pytest.raises(posts.PostLocked):
        posts.update_post(engine, ids["one_hour"], scheduled_at=None)
