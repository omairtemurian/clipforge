"""Slot generation of the bulk scheduler: posts per day, time slots, skip
days, start date and Europe/Zurich DST, with a fixed clock (`now`)."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from clipforge.scheduler.slots import day_slots, generate_slots, iter_slots
from schedule_fakes import ZURICH, local, rules, utc


def test_slots_follow_the_times_of_each_day() -> None:
    now = local(2026, 11, 2, 7, 0)
    assert generate_slots(rules(), now, 4) == [
        utc(2026, 11, 2, 8),
        utc(2026, 11, 2, 12),
        utc(2026, 11, 2, 17),
        utc(2026, 11, 3, 8),
    ]


def test_posts_per_day_uses_the_earliest_times() -> None:
    now = local(2026, 11, 2, 7, 0)
    slots = generate_slots(rules(posts_per_day=2), now, 4)
    assert slots == [
        utc(2026, 11, 2, 8),
        utc(2026, 11, 2, 12),
        utc(2026, 11, 3, 8),
        utc(2026, 11, 3, 12),
    ]


def test_only_slots_after_now_are_given() -> None:
    assert generate_slots(rules(), local(2026, 11, 2, 13, 0), 2) == [
        utc(2026, 11, 2, 17),
        utc(2026, 11, 3, 8),
    ]


def test_a_naive_now_is_utc() -> None:
    naive = datetime(2026, 11, 2, 12, 0)
    assert generate_slots(rules(), naive, 1) == [utc(2026, 11, 2, 17)]


def test_today_is_the_day_in_the_rules_timezone() -> None:
    # 23:30 UTC on Nov 1 is already Nov 2 in Zurich.
    now = utc(2026, 11, 1, 23, 30)
    assert generate_slots(rules(), now, 1) == [utc(2026, 11, 2, 8)]


def test_skip_days_have_no_slots() -> None:
    now = local(2026, 11, 6, 20, 0)  # a Friday evening
    slots = generate_slots(rules(skip_days=["sat", "sun"], posts_per_day=1), now, 2)
    assert slots == [utc(2026, 11, 9, 8), utc(2026, 11, 10, 8)]
    assert day_slots(rules(skip_days=["sat"]), date(2026, 11, 7)) == []


def test_start_date_in_the_future_is_the_first_day() -> None:
    now = local(2026, 11, 2, 7, 0)
    slots = generate_slots(rules(start_date="2026-11-05", posts_per_day=1), now, 1)
    assert slots == [utc(2026, 11, 5, 8)]


def test_start_date_in_the_past_starts_today() -> None:
    now = local(2026, 11, 2, 10, 0)
    slots = generate_slots(rules(start_date="2026-10-01", posts_per_day=1), now, 1)
    assert slots == [utc(2026, 11, 3, 8)]


def test_count_zero_and_negative() -> None:
    now = local(2026, 11, 2, 7, 0)
    assert generate_slots(rules(), now, 0) == []
    with pytest.raises(ValueError, match="negative"):
        generate_slots(rules(), now, -1)


def test_dst_spring_forward_moves_a_skipped_slot_by_the_gap() -> None:
    # Europe/Zurich skips 02:00-03:00 on Sunday 2026-03-29.
    zurich = rules(times=["02:30", "09:00"], start_date="2026-03-28")
    slots = generate_slots(zurich, local(2026, 3, 27, 12, 0), 6)
    assert slots == [
        utc(2026, 3, 28, 1, 30),  # 02:30 CET
        utc(2026, 3, 28, 8),  # 09:00 CET
        utc(2026, 3, 29, 1, 30),  # 02:30 does not exist: 03:30 CEST
        utc(2026, 3, 29, 7),  # 09:00 CEST
        utc(2026, 3, 30, 0, 30),  # 02:30 CEST
        utc(2026, 3, 30, 7),
    ]
    shifted = slots[2].astimezone(ZURICH)
    assert (shifted.hour, shifted.minute) == (3, 30)


def test_dst_spring_forward_keeps_the_day_in_order() -> None:
    # 02:30 becomes 03:30 CEST, after the 03:00 slot.
    zurich = rules(times=["02:30", "03:00"])
    assert day_slots(zurich, date(2026, 3, 29)) == [
        utc(2026, 3, 29, 1),
        utc(2026, 3, 29, 1, 30),
    ]


def test_dst_spring_forward_merges_a_slot_that_lands_on_another() -> None:
    zurich = rules(times=["02:30", "03:30"])
    assert day_slots(zurich, date(2026, 3, 29)) == [utc(2026, 3, 29, 1, 30)]
    assert len(day_slots(zurich, date(2026, 3, 30))) == 2


def test_dst_fall_back_uses_an_ambiguous_slot_once() -> None:
    # Europe/Zurich has 02:00-03:00 twice on Sunday 2026-10-25.
    zurich = rules(times=["02:30"], start_date="2026-10-24")
    slots = generate_slots(zurich, local(2026, 10, 23, 12, 0), 3)
    assert slots == [
        utc(2026, 10, 24, 0, 30),  # 02:30 CEST
        utc(2026, 10, 25, 0, 30),  # 02:30 CEST, the first 02:30
        utc(2026, 10, 26, 1, 30),  # 02:30 CET
    ]
    assert slots[1].astimezone(ZURICH).utcoffset() == timedelta(hours=2)
    assert local(2026, 10, 25, 2, 30, fold=1) not in slots


def test_dst_fall_back_after_the_first_occurrence_waits_a_day() -> None:
    zurich = rules(times=["02:30"])
    now = local(2026, 10, 25, 2, 15, fold=1)  # the second 02:15 (CET)
    assert generate_slots(zurich, now, 1) == [utc(2026, 10, 26, 1, 30)]


def test_slots_are_strictly_increasing_across_a_year() -> None:
    zurich = rules(times=["00:30", "02:30", "03:00", "23:30"], skip_days=["wed"])
    slots = list(iter_slots(zurich, utc(2026, 1, 1)))
    assert all(a < b for a, b in zip(slots, slots[1:], strict=False))
    assert not any(slot.astimezone(ZURICH).weekday() == 2 for slot in slots)
    assert {slot.tzinfo for slot in slots} == {UTC}


def test_seconds_in_times_are_kept() -> None:
    zurich = rules(times=[time(9, 0, 30)])
    assert day_slots(zurich, date(2026, 11, 2)) == [utc(2026, 11, 2, 8, 0, 30)]
