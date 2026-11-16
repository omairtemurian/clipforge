"""Tests for the posting worker's rate limits per account and per platform
and its quota guard (clipforge.scheduler.post_worker), on a fake wall
clock with a publisher of a made-up API (respx)."""

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
import respx
from clipforge import config, post_schedule, posts, usage
from clipforge.oauth import OAuthSession
from clipforge.publishers import registry
from clipforge.publishers.base import Publisher, PublishResult, Upload
from clipforge.publishers.quota import DailyQuota
from clipforge.token_store import TokenStore
from fake_clock import FakeWallClock
from post_worker_fakes import START, answer_published, connect, make_worker, queue
from social_fakes import CLIENT, ExamplePublisher
from sqlalchemy import Engine

# A daily quota of one upload that resets at midnight UTC.
QUOTA = DailyQuota("example_uploads", lambda: 1, ZoneInfo("UTC"), "ExampleTube upload")
MIDNIGHT = START.replace(hour=0) + timedelta(days=1)


@pytest.fixture
def no_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "post_account_gap_s", 0.0)


@pytest.fixture
def quota(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the "tiktok" (ExampleTube) entry QUOTA, one per upload."""
    entry = registry.PublisherEntry(lambda: None, (), ((QUOTA, 1.0),))
    monkeypatch.setitem(registry.ENTRIES, "tiktok", entry)


def test_an_account_starts_one_upload_per_gap(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
) -> None:
    answer_published(respx_mock)
    first_account = connect(engine, store, "a")
    first = queue(engine, clip_id, first_account)
    second = queue(engine, clip_id, first_account)
    other = queue(engine, clip_id, connect(engine, store, "b"))
    worker = make_worker(engine, store, clock)

    assert worker.poll() == [first, other]

    held = posts.get_post(engine, second)
    assert (held.status, held.attempts, held.error) == ("queued", 0, None)
    assert held.next_attempt_at == START + timedelta(seconds=60)
    clock.advance(seconds=59)
    assert worker.poll() == []
    clock.advance(seconds=1)
    assert worker.poll() == [second]


def test_an_account_posts_at_most_its_platforms_daily_cap_per_24_hours(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
    no_gap: None,
) -> None:
    monkeypatch.setitem(post_schedule.DAILY_POSTS, "tiktok", lambda: 2)
    answer_published(respx_mock)
    account_id = connect(engine, store, "a")
    worker = make_worker(engine, store, clock)
    first = queue(engine, clip_id, account_id)
    assert worker.poll() == [first]
    clock.advance(hours=3)
    ids = [queue(engine, clip_id, account_id) for _ in range(2)]

    assert worker.poll() == ids[:1]

    held = posts.get_post(engine, ids[1])
    assert held.next_attempt_at == START + timedelta(days=1)
    clock.now = START + timedelta(days=1)
    assert worker.poll() == ids[1:]


def test_a_platform_starts_at_most_its_hourly_uploads_over_all_accounts(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.settings, "post_platform_hourly", {"tiktok": 1})
    answer_published(respx_mock)
    first = queue(engine, clip_id, connect(engine, store, "a"))
    second = queue(engine, clip_id, connect(engine, store, "b"))
    worker = make_worker(engine, store, clock)

    assert worker.poll() == [first]

    assert posts.get_post(engine, second).next_attempt_at == START + timedelta(hours=1)
    clock.advance(hours=1)
    assert worker.poll() == [second]


def test_quota_guard_holds_posts_until_the_quota_resets(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
    quota: None,
) -> None:
    route = answer_published(respx_mock)
    usage.record(engine, QUOTA.kind, 1, at=START - timedelta(hours=1))
    post_id = queue(engine, clip_id, connect(engine, store, "a"))
    worker = make_worker(engine, store, clock)

    assert worker.poll() == []

    post = posts.get_post(engine, post_id)
    assert (post.status, post.attempts, post.next_attempt_at) == (
        "queued",
        0,
        MIDNIGHT,
    )
    assert post.error == "Waiting for the daily tiktok upload quota to reset."
    assert route.call_count == 0
    clock.now = MIDNIGHT
    assert worker.poll() == [post_id]
    assert posts.get_post(engine, post_id).status == "published"


class QuotaPublisher(ExamplePublisher):
    """ExampleTube that spends QUOTA before each upload, at START."""

    def upload(self, session: OAuthSession, upload: Upload) -> PublishResult:
        QUOTA.spend(1, START)
        return super().upload(session, upload)


def test_an_upload_refused_by_its_quota_waits_without_spending_an_attempt(
    engine: Engine,
    store: TokenStore,
    clip_id: int,
    clock: FakeWallClock,
    respx_mock: respx.MockRouter,
) -> None:
    usage.record(engine, QUOTA.kind, 1, at=START - timedelta(hours=1))
    post_id = queue(engine, clip_id, connect(engine, store, "a"))
    worker = make_worker(engine, store, clock)

    def quota_publisher(_platform: str) -> Publisher:
        return QuotaPublisher(CLIENT)

    worker.publisher_for = quota_publisher

    assert worker.poll() == [post_id]

    post = posts.get_post(engine, post_id)
    assert (post.status, post.attempts, post.attempted_at) == ("queued", 0, None)
    assert post.next_attempt_at == MIDNIGHT
    assert post.error is not None and "quota is used up" in post.error
    assert not respx_mock.calls
