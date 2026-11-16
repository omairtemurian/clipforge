"""Helpers of the scheduler tests: Europe/Zurich rules and wall-clock
times as aware UTC datetimes (the fixed clock the tests pass as now)."""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from clipforge.models import ScheduleRules

ZURICH = ZoneInfo("Europe/Zurich")


def rules(**fields: Any) -> ScheduleRules:
    """Return Europe/Zurich rules with 09:00, 13:00 and 18:00 slots."""
    values: dict[str, Any] = {
        "timezone": "Europe/Zurich",
        "times": ["09:00", "13:00", "18:00"],
    }
    values.update(fields)
    return ScheduleRules.model_validate(values)


def local(
    year: int, month: int, day: int, hour: int, minute: int = 0, *, fold: int = 0
) -> datetime:
    """Return a Zurich wall-clock time as an aware UTC datetime."""
    wall = datetime(year, month, day, hour, minute, tzinfo=ZURICH, fold=fold)
    return wall.astimezone(UTC)


def utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime:
    """Return an aware UTC datetime."""
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
