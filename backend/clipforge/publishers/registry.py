"""The publishers by platform (SPEC-v2 3.10).

ENTRIES maps a platform to how its publisher is made: factory() returns
the Publisher for the OAuth app set in the settings, or None while that app
is not configured (settings_keys names the settings to set) and quotas
are the daily quotas (with the units) that one upload spends, which the
posting worker checks before it starts one (quota guard). A platform
without an entry has no publisher yet: each platform's task (T46b-T48)
adds its entry. Tests replace ENTRIES items with monkeypatch.
"""

from collections.abc import Callable
from dataclasses import dataclass

from clipforge.models import SocialPlatform
from clipforge.publishers import facebook, instagram, tiktok, youtube
from clipforge.publishers.base import Publisher
from clipforge.publishers.quota import DailyQuota

QuotaUse = tuple[DailyQuota, float]


@dataclass(frozen=True)
class PublisherEntry:
    """How a platform's publisher is made, the settings it needs and the
    daily quotas an upload spends."""

    factory: Callable[[], Publisher | None]
    settings_keys: tuple[str, ...]
    quotas: tuple[QuotaUse, ...] = ()


class PublisherUnavailable(Exception):
    """A platform cannot be used: status and code are the API answer (501
    not_supported: no publisher; 412 needs_credentials: its OAuth app is
    not configured)."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


ENTRIES: dict[SocialPlatform, PublisherEntry] = {
    "youtube": PublisherEntry(
        youtube.from_settings, youtube.SETTINGS_KEYS, youtube.UPLOAD_QUOTAS
    ),
    "tiktok": PublisherEntry(tiktok.from_settings, tiktok.SETTINGS_KEYS),
    "instagram": PublisherEntry(instagram.from_settings, instagram.SETTINGS_KEYS),
    "facebook": PublisherEntry(facebook.from_settings, facebook.SETTINGS_KEYS),
}


def supported(platform: SocialPlatform) -> bool:
    """Return whether ClipForge has a publisher for platform."""
    return platform in ENTRIES


def settings_keys(platform: SocialPlatform) -> list[str]:
    """Return the settings that hold platform's OAuth app keys (none without
    a publisher)."""
    entry = ENTRIES.get(platform)
    return list(entry.settings_keys) if entry else []


def quotas(platform: SocialPlatform) -> tuple[QuotaUse, ...]:
    """Return the daily quotas (and units) one upload to platform spends."""
    entry = ENTRIES.get(platform)
    return entry.quotas if entry else ()


def configured(platform: SocialPlatform) -> bool:
    """Return whether platform's publisher exists and its OAuth app is set."""
    entry = ENTRIES.get(platform)
    return entry is not None and entry.factory() is not None


def publisher(platform: SocialPlatform) -> Publisher:
    """Return platform's publisher; PublisherUnavailable if there is none or
    its OAuth app is not configured."""
    entry = ENTRIES.get(platform)
    if entry is None:
        raise PublisherUnavailable(
            501, "not_supported", f"Publishing to {platform} is not available yet."
        )
    made = entry.factory()
    if made is None:
        keys = ", ".join(entry.settings_keys)
        raise PublisherUnavailable(
            412,
            "needs_credentials",
            f"Set {keys} (your own {platform} developer app, see README) "
            "to connect accounts.",
        )
    return made
