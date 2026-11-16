"""How often and how soon a post's upload is tried again (SPEC-v2 3.10:
retry/backoff).

After the n-th upload attempt of a post failed for a passing reason, the
next one waits base * 2^(n-1), at most cap (exponential backoff, no
jitter: one local app posts a few videos, so retries of many clients never
pile up at the same instant). The max_attempts-th failure is final.
"""

from dataclasses import dataclass
from datetime import timedelta

from clipforge import config


@dataclass(frozen=True)
class RetryPolicy:
    """Retries of a post's upload: at most max_attempts uploads, the n-th
    retry after base * 2^(n-1), never longer than cap."""

    max_attempts: int
    base: timedelta
    cap: timedelta

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base <= timedelta(0) or self.cap < self.base:
            raise ValueError("the backoff needs 0 < base <= cap")

    @classmethod
    def from_settings(cls) -> "RetryPolicy":
        """Return the policy of the settings post_max_attempts,
        post_retry_base_s and post_retry_max_s."""
        settings = config.settings
        base = timedelta(seconds=settings.post_retry_base_s)
        cap = timedelta(seconds=settings.post_retry_max_s)
        return cls(settings.post_max_attempts, base, max(base, cap))

    def delay(self, attempt: int) -> timedelta:
        """Return how long to wait after failed attempt number attempt
        (1 = the first upload) before the next."""
        if attempt < 1:
            raise ValueError("attempts are counted from 1")
        wait = self.base
        for _ in range(attempt - 1):
            if wait >= self.cap:
                break
            wait *= 2
        return min(wait, self.cap)

    def gives_up(self, attempt: int) -> bool:
        """Return whether a failure of attempt number attempt is final."""
        return attempt >= self.max_attempts
