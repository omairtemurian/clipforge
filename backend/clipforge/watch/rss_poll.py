"""When each polled source is read next: the 60 s fallback polling of the
watch (T28c).

FeedSchedule keeps one slot per source key (a YouTube channel id, a Twitch
login). A new key is due at once. After a read that worked the key is due
again after the interval with +-10 % jitter, so the reads of many sources
spread out instead of hitting the server together; after a failed read it
is due after min(interval * 2**failures, max_backoff), jittered too, and a
read that works again resets the failures. The slot also keeps the
validators (ETag / Last-Modified) of the last answer for a conditional
request. clock and rng are injectable for the fake-clock tests.
"""

import random
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from clipforge.sources.youtube_feed import Validators

JITTER = 0.1
MAX_BACKOFF_S = 1800.0


@dataclass
class _Slot:
    due: float
    failures: int = 0
    validators: Validators = field(default_factory=Validators)


class FeedSchedule:
    """The due times, backoff and validators of the polled sources."""

    def __init__(
        self,
        interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
        max_backoff: float = MAX_BACKOFF_S,
    ) -> None:
        self.interval = interval
        self.clock = clock
        self.rng = rng or random.Random()
        self.max_backoff = max_backoff
        self._slots: dict[str, _Slot] = {}

    def due(self, keys: Iterable[str]) -> list[str]:
        """Return the keys (in the given order) that are due now; keys the
        schedule has not seen are due. Slots of keys not given are dropped
        (the source is no longer watched)."""
        wanted = list(keys)
        for gone in set(self._slots) - set(wanted):
            del self._slots[gone]
        now = self.clock()
        return [key for key in wanted if self._slot(key).due <= now]

    def next_due(self, key: str) -> float:
        """Return the clock time at which key is due."""
        return self._slot(key).due

    def failures(self, key: str) -> int:
        """Return the number of failed reads of key in a row."""
        return self._slot(key).failures

    def validators(self, key: str) -> Validators:
        """Return the validators of key's last answer."""
        return self._slot(key).validators

    def succeeded(
        self,
        key: str,
        validators: Validators | None = None,
        interval: float | None = None,
    ) -> None:
        """Record a read of key that worked (validators: of its answer;
        interval: this time instead of the schedule's, e.g. the slower
        safety poll of a pushed source)."""
        slot = self._slot(key)
        slot.failures = 0
        if validators is not None:
            slot.validators = validators
        slot.due = self.clock() + self._jittered(interval or self.interval)

    def failed(self, key: str) -> None:
        """Record a failed read of key: back off exponentially."""
        slot = self._slot(key)
        slot.failures += 1
        delay = min(self.interval * 2**slot.failures, self.max_backoff)
        slot.due = self.clock() + self._jittered(delay)

    def _slot(self, key: str) -> _Slot:
        if key not in self._slots:
            self._slots[key] = _Slot(due=self.clock())
        return self._slots[key]

    def _jittered(self, delay: float) -> float:
        return delay * (1 + self.rng.uniform(-JITTER, JITTER))
