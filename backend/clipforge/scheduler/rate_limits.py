"""Posting rate limits (SPEC-v2 3.10) of the posting worker.

A RateLimit lets at most `most` uploads start within any `window`; given
the starts already made (attempted_at of the posts) it says when the next
upload may start. The limits of a post:

- its account: one upload start per post_account_gap_s seconds (TikTok
  allows 6 upload inits per minute per user token) and the platform's
  posts per account per day (post_schedule.DAILY_POSTS) per 24 h;
- its platform, over all accounts: post_platform_hourly[platform] upload
  starts per hour, when set (the owner's developer app limits).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from clipforge import config, post_schedule
from clipforge.models import SocialPlatform


@dataclass(frozen=True)
class RateLimit:
    """At most `most` upload starts within any window; label names the
    limit in the messages."""

    window: timedelta
    most: int
    label: str

    def free_at(self, starts: Iterable[datetime], now: datetime) -> datetime | None:
        """Return when the next upload may start given the earlier starts,
        or None if it may start at now."""
        recent = sorted(start for start in starts if start > now - self.window)
        if len(recent) < self.most:
            return None
        return recent[len(recent) - self.most] + self.window


def account_limits(platform: SocialPlatform) -> list[RateLimit]:
    """Return the rate limits of one account of platform."""
    limits = []
    gap = config.settings.post_account_gap_s
    if gap > 0:
        limits.append(RateLimit(timedelta(seconds=gap), 1, f"one upload per {gap:g} s"))
    cap = post_schedule.daily_cap(platform)
    if cap is not None:
        limits.append(RateLimit(timedelta(days=1), cap, f"{cap} posts per 24 h"))
    return limits


def platform_limits(platform: SocialPlatform) -> list[RateLimit]:
    """Return the rate limits of all accounts of platform together."""
    hourly = config.settings.post_platform_hourly.get(platform)
    if hourly is None:
        return []
    label = f"{hourly} {platform} uploads per hour"
    return [RateLimit(timedelta(hours=1), hourly, label)]


def wait_until(
    limits: Iterable[RateLimit], starts: list[datetime], now: datetime
) -> datetime | None:
    """Return the latest time any of limits holds the next upload back to,
    or None if none does."""
    frees = [limit.free_at(starts, now) for limit in limits]
    held = [moment for moment in frees if moment is not None and moment > now]
    return max(held, default=None)
