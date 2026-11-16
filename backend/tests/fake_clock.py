"""Clocks for the pollers, token expiry and posting worker tests (tests
only)."""

from datetime import datetime, timedelta


class FakeClock:
    """A clock that only moves when a test advances `now`."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakeWallClock:
    """A wall clock (aware datetimes) that only moves when a test calls
    advance()."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> datetime:
        """Move the clock forward by timedelta(**delta); the new time."""
        self.now += timedelta(**delta)
        return self.now
