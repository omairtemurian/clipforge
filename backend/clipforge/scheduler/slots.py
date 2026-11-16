"""Bulk scheduler core (SPEC-v2 3.10): the posting slots of ScheduleRules and
the allocation of clips to slots on several accounts at once.

Everything here is pure: the current time is a parameter (tests pass a
fixed one) and nothing touches the database. Slots are aware UTC datetimes;
the rules' days and times are wall-clock values in the rules' timezone,
turned into instants with zoneinfo's fold=0 (PEP 495):

- a time that the clocks skip (Europe/Zurich 2026-03-29 02:30) gets the
  offset from before the change, so it lands the length of the gap later
  (03:30 CEST); if that is another slot of the day, the day has one slot
  fewer;
- a time that happens twice (Europe/Zurich 2026-10-25 02:30) is used once,
  at its first occurrence (02:30 CEST).

A day of an account is a local calendar day in the rules' timezone.
"""

from collections import Counter, deque
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import islice
from zoneinfo import ZoneInfo

from clipforge.models import WEEKDAYS, ScheduleRules
from clipforge.watch.times import as_utc

# How far ahead slots are looked for (two years).
HORIZON_DAYS = 731


class NoFreeSlot(Exception):
    """The posts do not fit in the slots of the next HORIZON_DAYS days."""


@dataclass(frozen=True)
class AccountTarget:
    """An account that every clip of a bulk schedule is posted to;
    max_per_day is its own cap (e.g. a platform's daily post limit), on
    top of the rules' posts per day."""

    account_id: int
    max_per_day: int | None = None


@dataclass(frozen=True)
class SlotAssignment:
    """A clip posted to an account at scheduled_at (aware UTC)."""

    clip_id: int
    account_id: int
    scheduled_at: datetime


def slot_instant(day: date, at: time, zone: ZoneInfo) -> datetime:
    """Return the UTC instant of the wall-clock time `at` on `day` in zone
    (skipped times move forward by the gap; repeated times: the first)."""
    return datetime.combine(day, at, tzinfo=zone).astimezone(UTC)


def day_slots(rules: ScheduleRules, day: date) -> list[datetime]:
    """Return the slots of one day, earliest first (none on a skipped day)."""
    if WEEKDAYS[day.weekday()] in rules.skip_days:
        return []
    zone = ZoneInfo(rules.timezone)
    return sorted({slot_instant(day, at, zone) for at in rules.daily_times()})


def iter_slots(rules: ScheduleRules, now: datetime) -> Iterator[datetime]:
    """Yield the slots after now, earliest first, from the first posting
    day (start_date, or today in the rules' timezone) for HORIZON_DAYS
    days. A naive now is UTC."""
    moment = as_utc(now)
    today = moment.astimezone(ZoneInfo(rules.timezone)).date()
    first = max(rules.start_date or today, today)
    for offset in range(HORIZON_DAYS):
        for slot in day_slots(rules, first + timedelta(days=offset)):
            if slot > moment:
                yield slot


def generate_slots(rules: ScheduleRules, now: datetime, count: int) -> list[datetime]:
    """Return the next count slots after now (fewer at the horizon)."""
    if count < 0:
        raise ValueError("count must not be negative")
    return list(islice(iter_slots(rules, now), count))


def _caps(accounts: Sequence[AccountTarget], per_day: int) -> dict[int, int]:
    """Return each account's posts per day; refuse repeated accounts and
    caps below 1."""
    caps: dict[int, int] = {}
    for account in accounts:
        if account.account_id in caps:
            raise ValueError(f"account {account.account_id} is listed twice")
        if account.max_per_day is not None and account.max_per_day < 1:
            raise ValueError("max_per_day must be at least 1")
        caps[account.account_id] = min(per_day, account.max_per_day or per_day)
    return caps


def allocate(
    clip_ids: Sequence[int],
    accounts: Sequence[AccountTarget],
    rules: ScheduleRules,
    now: datetime,
    busy: Iterable[tuple[int, datetime]] = (),
) -> list[SlotAssignment]:
    """Schedule every clip on every account (several platforms at once).

    Each account gets the clips in the given order, each in its next free
    slot: a slot is free for an account while it has fewer posts that day
    than its cap (the rules' posts per day, lowered by max_per_day) and it
    has no post at that instant. busy lists the posts already scheduled
    as (account_id, scheduled_at); they count toward their day and hold
    their instant (naive means UTC). The result is ordered by time, then
    account id, so the same input always gives the same schedule. Raises
    NoFreeSlot when the clips do not fit within HORIZON_DAYS days.
    """
    if len(set(clip_ids)) != len(clip_ids):
        raise ValueError("a clip is listed twice")
    caps = _caps(accounts, len(rules.daily_times()))
    zone = ZoneInfo(rules.timezone)
    per_day: Counter[tuple[int, date]] = Counter()
    taken: set[tuple[int, datetime]] = set()
    for account_id, scheduled_at in busy:
        moment = as_utc(scheduled_at)
        per_day[account_id, moment.astimezone(zone).date()] += 1
        taken.add((account_id, moment))
    queues = {account_id: deque(clip_ids) for account_id in sorted(caps)}
    result: list[SlotAssignment] = []
    for slot in iter_slots(rules, now):
        if not any(queues.values()):
            return result
        day = slot.astimezone(zone).date()
        for account_id, queue in queues.items():
            if not queue or (account_id, slot) in taken:
                continue
            if per_day[account_id, day] >= caps[account_id]:
                continue
            result.append(SlotAssignment(queue.popleft(), account_id, slot))
            per_day[account_id, day] += 1
    if any(queues.values()):
        raise NoFreeSlot(f"the posts do not fit in the next {HORIZON_DAYS} days")
    return result
