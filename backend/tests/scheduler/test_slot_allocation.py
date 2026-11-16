"""Bulk allocation of the scheduler: every clip on every account, each
account's max per day, posts already scheduled, deterministic output."""

from datetime import datetime

import pytest
from clipforge.scheduler.slots import (
    HORIZON_DAYS,
    AccountTarget,
    NoFreeSlot,
    SlotAssignment,
    allocate,
)
from schedule_fakes import local, rules, utc

NOW = local(2026, 11, 2, 7, 0)  # Monday 07:00 in Zurich


def plan(result: list[SlotAssignment]) -> list[tuple[int, int, datetime]]:
    """Return the assignments as (clip, account, time) tuples."""
    return [(a.clip_id, a.account_id, a.scheduled_at) for a in result]


def test_every_clip_goes_to_every_account() -> None:
    accounts = [AccountTarget(1), AccountTarget(2)]
    result = allocate([10, 11], accounts, rules(), NOW)
    assert plan(result) == [
        (10, 1, utc(2026, 11, 2, 8)),
        (10, 2, utc(2026, 11, 2, 8)),
        (11, 1, utc(2026, 11, 2, 12)),
        (11, 2, utc(2026, 11, 2, 12)),
    ]


def test_each_account_keeps_to_its_max_per_day() -> None:
    accounts = [AccountTarget(1), AccountTarget(2, max_per_day=1)]
    result = allocate([10, 11, 12], accounts, rules(), NOW)
    assert plan(result) == [
        (10, 1, utc(2026, 11, 2, 8)),
        (10, 2, utc(2026, 11, 2, 8)),
        (11, 1, utc(2026, 11, 2, 12)),
        (12, 1, utc(2026, 11, 2, 17)),
        (11, 2, utc(2026, 11, 3, 8)),
        (12, 2, utc(2026, 11, 4, 8)),
    ]


def test_max_per_day_never_raises_the_rules_posts_per_day() -> None:
    accounts = [AccountTarget(1, max_per_day=5)]
    result = allocate([10, 11, 12], accounts, rules(posts_per_day=2), NOW)
    assert [a.scheduled_at for a in result] == [
        utc(2026, 11, 2, 8),
        utc(2026, 11, 2, 12),
        utc(2026, 11, 3, 8),
    ]


def test_skip_days_hold_for_every_account() -> None:
    friday = local(2026, 11, 6, 20, 0)
    accounts = [AccountTarget(1, max_per_day=1), AccountTarget(2)]
    weekdays = rules(skip_days=["sat", "sun"])
    result = allocate([10, 11], accounts, weekdays, friday)
    assert plan(result) == [
        (10, 1, utc(2026, 11, 9, 8)),
        (10, 2, utc(2026, 11, 9, 8)),
        (11, 2, utc(2026, 11, 9, 12)),
        (11, 1, utc(2026, 11, 10, 8)),
    ]


def test_scheduled_posts_count_and_hold_their_slot() -> None:
    busy = [
        (1, utc(2026, 11, 2, 8)),  # the 09:00 slot
        (1, datetime(2026, 11, 2, 9, 15)),  # naive: 10:15 in Zurich
        (2, utc(2026, 11, 2, 12)),
    ]
    accounts = [AccountTarget(1), AccountTarget(2)]
    result = allocate([10, 11], accounts, rules(), NOW, busy)
    assert plan(result) == [
        (10, 2, utc(2026, 11, 2, 8)),
        (10, 1, utc(2026, 11, 2, 12)),
        (11, 2, utc(2026, 11, 2, 17)),
        (11, 1, utc(2026, 11, 3, 8)),
    ]


def test_the_same_input_gives_the_same_schedule() -> None:
    forward = [AccountTarget(1), AccountTarget(2, 1), AccountTarget(3, 2)]
    backward = list(reversed(forward))
    first = allocate([12, 10, 11], forward, rules(), NOW)
    assert first == allocate([12, 10, 11], backward, rules(), NOW)
    assert first == allocate([12, 10, 11], forward, rules(), NOW)
    keys = [(a.scheduled_at, a.account_id) for a in first]
    assert keys == sorted(keys)
    assert [a.clip_id for a in first if a.account_id == 2] == [12, 10, 11]


def test_dst_days_are_counted_in_local_time() -> None:
    # Sunday 2026-10-25 (fall back) runs from 22:00 UTC on the 24th to
    # 23:00 UTC on the 25th: its 00:30 slot uses its one post a day.
    zurich = rules(times=["00:30", "23:30"])
    sunday = local(2026, 10, 25, 0, 0)
    once = [AccountTarget(1, max_per_day=1)]
    result = allocate([10, 11, 12], once, zurich, sunday)
    assert [a.scheduled_at for a in result] == [
        utc(2026, 10, 24, 22, 30),  # Sunday 00:30 CEST
        utc(2026, 10, 25, 23, 30),  # Monday 00:30 CET
        utc(2026, 10, 26, 23, 30),  # Tuesday 00:30 CET
    ]


def test_nothing_to_schedule() -> None:
    assert allocate([], [AccountTarget(1)], rules(), NOW) == []
    assert allocate([10], [], rules(), NOW) == []


def test_bad_input_is_refused() -> None:
    with pytest.raises(ValueError, match="clip"):
        allocate([10, 10], [AccountTarget(1)], rules(), NOW)
    with pytest.raises(ValueError, match="account 1"):
        allocate([10], [AccountTarget(1), AccountTarget(1)], rules(), NOW)
    with pytest.raises(ValueError, match="max_per_day"):
        allocate([10], [AccountTarget(1, max_per_day=0)], rules(), NOW)


def test_posts_that_do_not_fit_in_the_horizon() -> None:
    clips = list(range(HORIZON_DAYS + 1))
    one_a_day = rules(posts_per_day=1)
    with pytest.raises(NoFreeSlot):
        allocate(clips, [AccountTarget(1)], one_a_day, NOW)
    assert len(allocate(clips[:-2], [AccountTarget(1)], one_a_day, NOW)) == (
        HORIZON_DAYS - 1
    )
