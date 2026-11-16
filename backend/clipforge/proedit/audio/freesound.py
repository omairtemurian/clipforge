"""Freesound sounds for Pro Edit (SPEC-v3 5.1, 5.6; endpoints, auth and
limits checked 2026-11-04 in https://freesound.org/docs/api/, docs/decisions.md
TASK-217).

GET https://freesound.org/apiv2/search/ (the old /apiv2/search/text/ was
deprecated in November 2025) with the API key as `Authorization: Token <key>`;
`filter` takes Solr syntax (`tag:whoosh duration:[0.1 TO 3]
license:("Creative Commons 0" OR "Attribution")`); `fields` picks the
metadata of each result, so one request lists everything. The original file
(/apiv2/sounds/<id>/download/) needs OAuth2, which ClipForge does not use:
the token alone gives the HQ preview (128 kbps MP3 on the CDN, no key), and
that is what is stored, with the sound's license and credit. Only CC0 and CC
BY sounds are accepted: the filter asks for them and the license of every
returned sound is checked again (licenses.license_label). The API allows 60
requests per minute and 2000 per day per user; RateLimiter keeps below the
first and a 429 is reported as "rate limit reached". Previews come from the
CDN, which is not rate limited by the API.
"""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from clipforge import config
from clipforge.asset_rows import AssetRow
from clipforge.assets import add_asset, update_asset
from clipforge.ffmpeg import FFmpegError, ffprobe_json
from clipforge.models import Asset, AssetKind
from clipforge.pipeline.step import StepError
from clipforge.proedit.audio.licenses import is_allowed, license_label
from clipforge.proedit.audio.tagging import tag_asset
from clipforge.stock.base import (
    TIMEOUT,
    ProviderDisabled,
    StockError,
    fetch_file,
    get_json,
)

logger = logging.getLogger(__name__)
LABEL = "Freesound"
API_URL = "https://freesound.org/apiv2"
SEARCH_URL = f"{API_URL}/search/"
SITE = "https://freesound.org/"
FIELDS = "id,name,tags,username,license,url,duration,previews"
FILTER_LICENSE = 'license:("Creative Commons 0" OR "Attribution")'
PREVIEW_KEYS = ("preview-hq-mp3", "preview-hq-ogg", "preview-lq-mp3")
MIN_PAGE, MAX_PAGE = 1, 150
FREESOUND_TAG = "freesound"
MAX_QUERY_CHARS = 100
REQUESTS_PER_MINUTE = 60
MAX_WAIT_S = 10.0
SoundKind = Literal["sfx", "music", "audio"]


class LicenseRejected(StockError):
    """A Freesound sound is not CC0 or CC BY (or has no preview to store)."""


class FreesoundSound(BaseModel):
    """A Freesound sound that can be stored: its id, title, uploader, tags,
    length, license label (CC0 or CC BY only), page URL, the HQ preview that
    gets downloaded and the credit text the asset keeps."""

    id: int
    name: str
    username: str
    tags: list[str]
    duration_s: float = Field(ge=0)
    license: str
    page_url: str
    preview_url: str
    attribution: str


class FreesoundStatus(BaseModel):
    """Whether the Freesound library is on; message says how to turn it on."""

    enabled: bool
    message: str


def disabled_message() -> str:
    """Return what to do to turn Freesound on."""
    return (
        "Add a Freesound key: set FREESOUND_API_KEY in .env.local "
        "(a free key at https://freesound.org/apiv2/apply)"
    )


def status() -> FreesoundStatus:
    """Return whether FREESOUND_API_KEY is set."""
    enabled = bool(config.settings.freesound_api_key)
    return FreesoundStatus(
        enabled=enabled, message="" if enabled else disabled_message()
    )


class RateLimiter:
    """Keeps requests below calls per per_s seconds: acquire() waits for a
    free slot, at most max_wait_s, else raises StockError. Thread-safe."""

    def __init__(
        self,
        calls: int = REQUESTS_PER_MINUTE,
        per_s: float = 60.0,
        max_wait_s: float = MAX_WAIT_S,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._calls, self._per_s, self._max_wait_s = calls, per_s, max_wait_s
        self._clock, self._sleep = clock, sleep
        self._stamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Take a slot, waiting for one if all are used."""
        with self._lock:
            now = self._clock()
            while self._stamps and now - self._stamps[0] >= self._per_s:
                self._stamps.popleft()
            if len(self._stamps) >= self._calls:
                wait = self._stamps[0] + self._per_s - now
                if wait > self._max_wait_s:
                    raise StockError(
                        f"{LABEL} rate limit reached; try again in {wait:.0f} s"
                    )
                self._sleep(wait)
                self._stamps.popleft()
                now = self._clock()
            self._stamps.append(now)


limiter = RateLimiter()


def attribution_text(name: str, username: str, page_url: str, label: str) -> str:
    """Return the credit of a sound: its title, uploader, page and license."""
    return f'"{name}" by {username} on Freesound ({page_url}), {label}'


def tag_term(tag: str) -> str:
    """Return tag as a Freesound tag (lower case, words joined with dashes);
    raises ValueError if it has anything but letters, digits, `-` and `_`."""
    term = "-".join(tag.lower().split())
    if not term or not all(c.isalnum() or c in "-_" for c in term):
        raise ValueError(f"not a Freesound tag: {tag!r}")
    return term


def search_filter(
    tags: Sequence[str], min_duration_s: float, max_duration_s: float | None
) -> str:
    """Return the Freesound `filter` of a search: every tag, the length
    range and the CC0/CC BY license filter."""
    terms = [f"tag:{tag_term(tag)}" for tag in tags]
    if min_duration_s > 0 or max_duration_s is not None:
        high = "*" if max_duration_s is None else f"{max_duration_s:g}"
        terms.append(f"duration:[{min_duration_s:g} TO {high}]")
    return " ".join([*terms, FILTER_LICENSE])


def parse_sound(item: Any) -> FreesoundSound | None:
    """Return the sound of a Freesound result (search or instance), None if
    it is not CC0 or CC BY (checked on the returned license, whatever the
    filter asked for) or has no HTTPS preview."""
    if not isinstance(item, dict) or not isinstance(item.get("id"), int):
        return None
    label = license_label(item.get("license"))
    previews = item.get("previews")
    preview = next(
        (
            url
            for key in PREVIEW_KEYS
            if isinstance(previews, dict)
            and isinstance(url := previews.get(key), str)
            and url.startswith("https://")
        ),
        None,
    )
    if label is None or preview is None:
        return None
    sound_id, username = item["id"], str(item.get("username") or "")
    url = item.get("url")
    page_url = (
        url
        if isinstance(url, str) and url.startswith(SITE)
        else f"{SITE}people/{username}/sounds/{sound_id}/"
    )
    name = str(item.get("name") or f"Sound {sound_id}")
    tags = item.get("tags")
    return FreesoundSound(
        id=sound_id,
        name=name,
        username=username,
        tags=[t for t in tags if isinstance(t, str)] if isinstance(tags, list) else [],
        duration_s=float(item.get("duration") or 0),
        license=label,
        page_url=page_url,
        preview_url=preview,
        attribution=attribution_text(name, username, page_url, label),
    )


class FreesoundClient:
    """Searches Freesound and reads sounds with the owner's API key."""

    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        if not api_key:
            raise ProviderDisabled(disabled_message())
        self._headers = {"Authorization": f"Token {api_key}"}
        self._transport = transport
        self._limiter = limiter if rate_limiter is None else rate_limiter

    def search(
        self,
        *,
        tags: Sequence[str] = (),
        query: str = "",
        min_duration_s: float = 0,
        max_duration_s: float | None = None,
        page_size: int = 15,
    ) -> list[FreesoundSound]:
        """Return the CC0 and CC BY sounds that have all tags and match query,
        within the length range, best match first; sounds with another
        license are left out. Raises ValueError without a tag and a query
        (or for a tag with other characters than letters, digits, `-`, `_`)
        and StockError if Freesound cannot be read."""
        text = query.strip()[:MAX_QUERY_CHARS]
        if not tags and not text:
            raise ValueError("search needs a tag or a query")
        params: dict[str, str | int] = {
            "query": text,
            "filter": search_filter(tags, min_duration_s, max_duration_s),
            "fields": FIELDS,
            "page_size": max(MIN_PAGE, min(page_size, MAX_PAGE)),
        }
        body = self._get(SEARCH_URL, params)
        results = body.get("results")
        found = results if isinstance(results, list) else []
        return [s for item in found if (s := parse_sound(item)) is not None]

    def sound(self, sound_id: int) -> FreesoundSound:
        """Return sound sound_id; raises LicenseRejected if it is not CC0 or
        CC BY or has no preview, StockError if it cannot be read."""
        body = self._get(f"{API_URL}/sounds/{sound_id}/", {"fields": FIELDS})
        found = parse_sound(body)
        if found is None:
            raise LicenseRejected(
                f"Freesound sound {sound_id} is not CC0 or CC BY "
                f"(license {body.get('license')!r}) or has no preview: not used"
            )
        return found

    def _get(self, url: str, params: dict[str, str | int]) -> dict[str, Any]:
        """GET url within the rate limit (a metered API call)."""
        self._limiter.acquire()
        with httpx.Client(transport=self._transport, timeout=TIMEOUT) as http:
            return get_json(http, LABEL, url, params=params, headers=self._headers)


def freesound_dir() -> Path:
    """Return the directory of downloaded Freesound previews."""
    return config.settings.data_dir / "audio" / FREESOUND_TAG


def download_sound(
    session: Session,
    sound: FreesoundSound,
    *,
    kind: AssetKind = "sfx",
    category: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> Asset:
    """Download the preview of sound into data/audio/freesound/ and add it to
    the asset library (kind; tags "freesound" and the sound's) with its
    license, credit, page URL and download time, analyzed and tagged
    (tagging.tag_asset; category wins over the found one); return the asset.

    A sound that was downloaded before (same page URL, file still there) is
    returned without a new download. Raises LicenseRejected if sound's
    license is not CC0 or CC BY, StockError if the download fails or the file
    has no audio; nothing is kept then.
    """
    if not is_allowed(sound.license):
        raise LicenseRejected(f"{sound.license} is not CC0 or CC BY: not downloaded")
    existing = session.exec(
        select(AssetRow).where(col(AssetRow.source_url) == sound.page_url)
    ).first()
    if existing is not None and Path(existing.path).is_file():
        return existing.to_model()
    folder = freesound_dir()
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(httpx.URL(sound.preview_url).path).suffix or ".mp3"
    dest = folder / f"{sound.id}{suffix}"
    part = dest.with_name(dest.name + ".part")
    try:
        fetch_file(sound.preview_url, part, transport)
        streams = ffprobe_json(part).get("streams", [])
        if not any(s.get("codec_type") == "audio" for s in streams):
            raise FFmpegError("no audio stream")
    except FFmpegError as exc:
        part.unlink(missing_ok=True)
        raise StockError(f"the Freesound download is not audio: {exc}") from exc
    except StockError:
        part.unlink(missing_ok=True)
        raise
    part.replace(dest)
    asset = add_asset(
        session,
        kind,
        str(dest),
        sound.license,
        attribution=sound.attribution,
        source_url=sound.page_url,
        tags=list(dict.fromkeys([FREESOUND_TAG, *sound.tags])),
    )
    asset = update_asset(
        session, asset.id, category=category, downloaded_at=datetime.now(UTC)
    )
    try:
        return tag_asset(session, asset)
    except StepError as exc:
        logger.warning("Freesound sound %d is not analyzed: %s", sound.id, exc)
        return asset
