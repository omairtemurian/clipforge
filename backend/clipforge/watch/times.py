"""Wall-clock helpers of the watch. SQLite gives back naive datetimes (UTC
by convention), the feeds and APIs aware ones; as_utc makes both aware."""

from collections.abc import Callable
from datetime import UTC, datetime

WallClock = Callable[[], datetime]


def utc_now() -> datetime:
    """Return the current time, timezone-aware."""
    return datetime.now(UTC)


def as_utc(moment: datetime) -> datetime:
    """Return moment as an aware UTC datetime (naive means UTC)."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)
