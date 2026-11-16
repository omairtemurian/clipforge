"""Tests for the pure parts of the posting worker: the retry policy's
backoff (clipforge.scheduler.retry), a rate limit's next free start
(clipforge.scheduler.rate_limits) and a daily quota's reset time."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from clipforge.publishers.quota import DailyQuota
from clipforge.scheduler.rate_limits import RateLimit, wait_until
from clipforge.scheduler.retry import RetryPolicy

NOW = datetime(2030, 1, 15, 9, 0, tzinfo=UTC)


def test_backoff_doubles_from_its_base_up_to_its_cap() -> None:
    policy = RetryPolicy(10, timedelta(minutes=1), timedelta(minutes=10))

    delays = [policy.delay(attempt).total_seconds() / 60 for attempt in range(1, 8)]

    assert delays == [1, 2, 4, 8, 10, 10, 10]
    assert policy.delay(10_000) == timedelta(minutes=10)
    assert [policy.gives_up(n) for n in (1, 9, 10, 11)] == [False, False, True, True]


@pytest.mark.parametrize(
    ("attempts", "base", "cap"),
    [(0, 60, 60), (3, 0, 60), (3, 120, 60)],
)
def test_retry_policy_refuses_impossible_settings(
    attempts: int, base: float, cap: float
) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(attempts, timedelta(seconds=base), timedelta(seconds=cap))


def test_rate_limit_frees_a_start_when_the_oldest_counted_leaves_the_window() -> None:
    limit = RateLimit(timedelta(hours=1), 2, "2 per hour")
    starts = [NOW - timedelta(minutes=50), NOW - timedelta(minutes=20)]

    assert limit.free_at(starts[1:], NOW) is None
    assert limit.free_at(starts, NOW) == NOW + timedelta(minutes=10)
    assert limit.free_at([NOW - timedelta(hours=2), *starts[1:]], NOW) is None


def test_wait_until_takes_the_latest_limit_that_holds() -> None:
    gap = RateLimit(timedelta(minutes=1), 1, "gap")
    daily = RateLimit(timedelta(days=1), 1, "daily")
    starts = [NOW - timedelta(seconds=30)]

    assert wait_until([gap, daily], starts, NOW) == starts[0] + timedelta(days=1)
    assert wait_until([gap], [NOW - timedelta(minutes=5)], NOW) is None
    assert wait_until([], starts, NOW) is None


def test_a_quota_resets_at_the_next_local_midnight_across_dst() -> None:
    pacific = ZoneInfo("America/Los_Angeles")
    quota = DailyQuota("q", lambda: 1, pacific, "q")
    # 2030-03-10 is the spring-forward day in the US (23 hours long).
    before = datetime(2030, 3, 10, 1, 0, tzinfo=pacific)

    reset = quota.next_reset(before)

    assert reset == datetime(2030, 3, 11, 0, 0, tzinfo=pacific).astimezone(UTC)
    assert reset - quota.day_start(before) == timedelta(hours=23)
