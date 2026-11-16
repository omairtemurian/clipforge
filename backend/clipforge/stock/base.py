"""What the stock B-roll providers share (SPEC-v2 3.6): errors, the metering
of API requests, a 24 h cache of search results and the download of a clip
into the asset library.

Every search request is one API call of the usage meter (usage.API_CALLS) for
the project of the current usage.recording() context; outside one nothing is
metered. A download comes from the providers' CDN, not from their API, so it
is not counted and does not carry the API key.
"""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, TypeVar

import httpx
from sqlmodel import Session, col, select

from clipforge import config, usage
from clipforge.asset_rows import AssetRow
from clipforge.assets import add_asset
from clipforge.ffmpeg import FFmpegError, probe_media
from clipforge.models import Asset, StockClip, StockSource

T = TypeVar("T")

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
CHUNK_BYTES = 1 << 20
STOCK_TAG = "stock"
# The short side (px) a B-roll file should have at least: Full HD, so that a
# full-screen cutaway in a 1080 x 1920 clip is sharp.
TARGET_SHORT_SIDE = 1080
# Pixabay asks that API results are cached for 24 hours.
CACHE_SECONDS = 24 * 3600


class StockError(RuntimeError):
    """A stock search or download failed; the message says why."""


class ProviderDisabled(StockError):
    """A provider has no API key; the message says where to put it."""


class StockProvider(Protocol):
    """A stock video provider."""

    name: StockSource

    def search(
        self,
        query: str,
        *,
        orientation: str | None = None,
        min_duration_s: float = 0,
        per_page: int = 15,
    ) -> list[StockClip]:
        """Return the videos that match query (orientation "landscape",
        "portrait" or "square"), at least min_duration_s long."""
        ...


class SearchCache:
    """Search results kept for CACHE_SECONDS, by request."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._items: dict[tuple[object, ...], tuple[float, list[StockClip]]] = {}

    def get(self, key: tuple[object, ...]) -> list[StockClip] | None:
        """Return the results stored for key, None if none or too old."""
        found = self._items.get(key)
        if found is None:
            return None
        stored_at, clips = found
        if self._clock() - stored_at >= CACHE_SECONDS:
            del self._items[key]
            return None
        return [clip.model_copy() for clip in clips]

    def put(self, key: tuple[object, ...], clips: list[StockClip]) -> None:
        """Store the results of key."""
        self._items[key] = (self._clock(), [clip.model_copy() for clip in clips])

    def clear(self) -> None:
        """Forget everything."""
        self._items.clear()


def count_api_call() -> None:
    """Record one API call for the current usage.recording() context."""
    recorder = usage.current()
    if recorder is not None:
        usage.record(
            recorder.engine, usage.API_CALLS, 1, project_id=recorder.project_id
        )


def get_json(http: httpx.Client, label: str, url: str, **kwargs: Any) -> dict[str, Any]:
    """GET url (a metered API call) and return its JSON object.

    Raises StockError for a network failure, a refused key (401, 403), the
    rate limit (429), any other HTTP error, or an answer that is not a JSON
    object. label names the provider in the message.
    """
    count_api_call()
    try:
        response = http.get(url, **kwargs)
    except httpx.HTTPError as exc:
        raise StockError(f"could not reach {label}: {exc}") from exc
    if response.status_code in (401, 403):
        raise StockError(f"{label} refused the API key (HTTP {response.status_code})")
    if response.status_code == 429:
        raise StockError(f"{label} rate limit reached; try again later")
    if not response.is_success:
        raise StockError(f"{label} answered HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError as exc:
        raise StockError(f"{label} answered something that is not JSON") from exc
    if not isinstance(body, dict):
        raise StockError(f"{label} answered an unexpected JSON value")
    return body


def best_file(
    files: list[tuple[int, int, T]], short_side: int = TARGET_SHORT_SIDE
) -> T | None:
    """Return the item of (width, height, item) triples with the smallest
    short side of at least short_side, else the one with the largest; None
    if there are none."""
    if not files:
        return None
    big_enough = [f for f in files if min(f[0], f[1]) >= short_side]
    if big_enough:
        return min(big_enough, key=lambda f: (min(f[0], f[1]), f[0] * f[1]))[2]
    return max(files, key=lambda f: (min(f[0], f[1]), f[0] * f[1]))[2]


def stock_dir() -> Path:
    """Return the directory of downloaded stock videos."""
    return config.settings.data_dir / "stock"


def download_clip(
    session: Session,
    clip: StockClip,
    *,
    transport: httpx.BaseTransport | None = None,
) -> Asset:
    """Download clip into data/stock/<provider>/ and add it to the asset
    library, with its license, attribution and page URL (tags: "stock", the
    provider, the clip's tags); return the asset.

    A clip that was downloaded before (same page URL, file still there) is
    returned without a new download. Raises StockError if the download fails
    or the file is not a video; nothing is kept then.
    """
    existing = session.exec(
        select(AssetRow).where(col(AssetRow.source_url) == clip.page_url)
    ).first()
    if existing is not None and Path(existing.path).is_file():
        return existing.to_model()
    if not clip.download_url.startswith("https://"):
        raise StockError("a stock download must be an https link")
    folder = stock_dir() / clip.provider
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{clip.provider_id}.mp4"
    part = dest.with_name(dest.name + ".part")
    try:
        fetch_file(clip.download_url, part, transport)
        probe_media(part)
    except FFmpegError as exc:
        part.unlink(missing_ok=True)
        raise StockError(f"the stock download is not a video: {exc}") from exc
    except StockError:
        part.unlink(missing_ok=True)
        raise
    part.replace(dest)
    tags = [STOCK_TAG, clip.provider, *clip.tags]
    return add_asset(
        session,
        "video",
        str(dest),
        clip.license,
        attribution=clip.attribution,
        source_url=clip.page_url,
        tags=list(dict.fromkeys(tags)),
    )


def fetch_file(url: str, dest: Path, transport: httpx.BaseTransport | None) -> None:
    """Stream url into dest; StockError if it fails."""
    try:
        with (
            httpx.Client(
                transport=transport, timeout=TIMEOUT, follow_redirects=True
            ) as http,
            http.stream("GET", url) as response,
        ):
            if not response.is_success:
                raise StockError(
                    f"the stock download answered HTTP {response.status_code}"
                )
            with dest.open("wb") as handle:
                for chunk in response.iter_bytes(CHUNK_BYTES):
                    handle.write(chunk)
    except httpx.HTTPError as exc:
        raise StockError(f"the stock download failed: {exc}") from exc
