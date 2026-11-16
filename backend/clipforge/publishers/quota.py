"""Daily API quotas of the social platforms (SPEC-v2 3.10: quota guard).

A DailyQuota is one quota bucket of the owner's developer app: its usage
kind in the usage meter (clipforge.usage), the units it allows per day and
the time zone whose midnight resets it. spend() is called before each
request: it refuses (QuotaExceeded, a retryable PublishError) a request
that would go over the day's budget, and records the units otherwise, so
the meter shows them per project. A platform charges a request even when
it fails, so the units are recorded before it is sent.

The day's total is read from the usage records of the current
usage.recording() context (the publish run and the account callback set
one); outside a context nothing is metered or guarded.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, func
from sqlmodel import Session, col, select

from clipforge import usage
from clipforge.asset_rows import UsageRecordRow
from clipforge.publishers.base import PublishError


class QuotaExceeded(PublishError):
    """A request would go over a daily quota; it may be sent after the
    quota resets at retry_at (retryable)."""

    def __init__(self, message: str, retry_at: datetime) -> None:
        super().__init__(message, retryable=True)
        self.retry_at = retry_at


@dataclass(frozen=True)
class DailyQuota:
    """A daily quota bucket: kind is its usage kind, limit() the units it
    allows per day (read when used, so a settings change applies), zone the
    time zone whose midnight resets it, label how messages name it."""

    kind: str
    limit: Callable[[], float]
    zone: ZoneInfo
    label: str

    def day_start(self, now: datetime) -> datetime:
        """Return the start (UTC) of the quota day that now is in."""
        local = now.astimezone(self.zone)
        midnight = datetime(local.year, local.month, local.day, tzinfo=self.zone)
        return midnight.astimezone(UTC)

    def next_reset(self, now: datetime) -> datetime:
        """Return the start (UTC) of the quota day after the one now is in."""
        start = self.day_start(now).astimezone(self.zone)
        return self.day_start(start + timedelta(days=1, hours=12))

    def allows(self, engine: Engine, units: float, now: datetime) -> bool:
        """Return whether units more fit in the quota day of now."""
        return self.used(engine, now) + units <= self.limit()

    def used(self, engine: Engine, now: datetime) -> float:
        """Return the units recorded on the quota day of now."""
        start = self.day_start(now)
        end = self.next_reset(now)
        with Session(engine) as session:
            total = session.exec(
                select(func.sum(UsageRecordRow.units)).where(
                    col(UsageRecordRow.kind) == self.kind,
                    col(UsageRecordRow.at) >= start,
                    col(UsageRecordRow.at) < end,
                )
            ).one()
        return float(total or 0)

    def spend(self, units: float, now: datetime) -> None:
        """Record units of a request about to be sent; QuotaExceeded (and
        nothing recorded) if the day's total would go over limit()."""
        recorder = usage.current()
        if recorder is None:
            return
        limit = self.limit()
        used = self.used(recorder.engine, now)
        if used + units > limit:
            raise QuotaExceeded(
                f"The daily {self.label} quota is used up ({used:g} of "
                f"{limit:g}); it resets at midnight {self.zone.key} time.",
                self.next_reset(now),
            )
        usage.record(
            recorder.engine,
            self.kind,
            units,
            project_id=recorder.project_id,
            at=now.astimezone(UTC),
        )
