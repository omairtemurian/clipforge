"""Validation of the bulk scheduler's rules (ScheduleRules)."""

from datetime import time
from typing import Any

import pytest
from pydantic import ValidationError
from schedule_fakes import rules


def test_rules_parse_wall_clock_times_in_order() -> None:
    parsed = rules(times=["18:00", "09:00", "13:30"], posts_per_day=2)
    assert parsed.times == [time(9), time(13, 30), time(18)]
    assert parsed.daily_times() == [time(9), time(13, 30)]
    assert rules().daily_times() == [time(9), time(13), time(18)]


def test_skip_days_are_kept_once_in_week_order() -> None:
    assert rules(skip_days=["sun", "mon", "sun"]).skip_days == ["mon", "sun"]


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"timezone": "Mars/Olympus"}, "not a known timezone"),
        ({"timezone": "../etc/passwd"}, "not a known timezone"),
        ({"times": []}, "at least 1"),
        ({"times": ["09:00", "09:00"]}, "must not repeat"),
        ({"times": ["09:00+02:00"]}, "without a UTC offset"),
        ({"posts_per_day": 4}, "more than the number of times"),
        ({"posts_per_day": 0}, "greater than or equal to 1"),
        (
            {"skip_days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]},
            "every day of the week",
        ),
        ({"skip_days": ["monday"]}, "Input should be"),
        ({"slots": 3}, "Extra inputs"),
    ],
)
def test_bad_rules_are_refused(fields: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        rules(**fields)
