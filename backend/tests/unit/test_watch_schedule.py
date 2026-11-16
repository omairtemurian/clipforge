"""Tests for the polling schedule of the watch (clipforge.watch.rss_poll):
new sources are due at once, reads are 60 s apart with +-10 % jitter,
failures back off exponentially up to 30 min, validators are kept, and
dropped sources are forgotten. A fake clock and a seeded rng."""

import random

from clipforge.sources.youtube_feed import Validators
from clipforge.watch.rss_poll import FeedSchedule
from fake_clock import FakeClock


def _schedule(clock: FakeClock, seed: int = 7) -> FeedSchedule:
    return FeedSchedule(60.0, clock=clock, rng=random.Random(seed))


def test_a_new_source_is_due_at_once_then_after_the_jittered_interval() -> None:
    clock = FakeClock()
    schedule = _schedule(clock)

    assert schedule.due(["a", "b"]) == ["a", "b"]
    schedule.succeeded("a")
    delay = schedule.next_due("a") - clock.now

    assert 54.0 <= delay <= 66.0
    clock.now += delay - 0.01
    assert schedule.due(["a", "b"]) == ["b"]
    clock.now += 0.01
    assert schedule.due(["a", "b"]) == ["a", "b"]


def test_the_jitter_spreads_the_reads_within_ten_percent() -> None:
    clock = FakeClock()
    schedule = _schedule(clock)
    delays = []
    for key in (str(n) for n in range(200)):
        schedule.succeeded(key)
        delays.append(schedule.next_due(key) - clock.now)

    assert min(delays) >= 54.0 and max(delays) <= 66.0
    assert max(delays) - min(delays) > 6.0  # not all at the same time


def test_failures_back_off_exponentially_up_to_30_minutes_then_reset() -> None:
    clock = FakeClock()
    schedule = FeedSchedule(60.0, clock=clock, rng=random.Random(1))
    delays = []
    for _ in range(7):
        schedule.failed("a")
        delays.append(schedule.next_due("a") - clock.now)

    for delay, base in zip(delays, [120, 240, 480, 960, 1800, 1800, 1800], strict=True):
        assert base * 0.9 <= delay <= base * 1.1
    assert schedule.failures("a") == 7

    schedule.succeeded("a")
    assert schedule.failures("a") == 0
    assert schedule.next_due("a") - clock.now <= 66.0


def test_validators_are_kept_and_a_longer_interval_can_be_asked() -> None:
    clock = FakeClock()
    schedule = _schedule(clock)
    tagged = Validators(etag='"v1"')

    schedule.succeeded("a", tagged, interval=900.0)
    schedule.succeeded("b", tagged)
    schedule.succeeded("b")

    assert schedule.validators("a") == tagged == schedule.validators("b")
    assert 810.0 <= schedule.next_due("a") - clock.now <= 990.0


def test_sources_no_longer_given_are_forgotten() -> None:
    clock = FakeClock()
    schedule = _schedule(clock)
    schedule.succeeded("a", Validators(etag='"v1"'))

    assert schedule.due(["b"]) == ["b"]
    assert schedule.validators("a") == Validators()
    assert schedule.due(["a"]) == ["a"]
