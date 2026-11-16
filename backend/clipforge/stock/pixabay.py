"""Pixabay stock videos (SPEC-v2 3.6; endpoints, key parameter, caching rule
and license checked 2026-11-02 in https://pixabay.com/api/docs/ and
https://pixabay.com/service/license-summary/, docs/decisions.md TASK-119).

GET https://pixabay.com/api/videos/ with the key as the `key` query
parameter; 100 requests per 60 s per key. Pixabay asks that results are
cached for 24 hours (SearchCache), that users are shown where the videos
come from, and that videos are stored on our side rather than hotlinked
(downloads go to data/stock). The Content License allows free, commercial
use and editing without attribution, but not selling a video unaltered.
"""

from typing import Any

import httpx

from clipforge.models import StockClip, StockSource
from clipforge.stock.base import (
    TIMEOUT,
    ProviderDisabled,
    SearchCache,
    best_file,
    get_json,
)

LABEL = "Pixabay"
SEARCH_URL = "https://pixabay.com/api/videos/"
LICENSE = "Pixabay Content License"
MIN_PER_PAGE, MAX_PER_PAGE = 3, 200

cache = SearchCache()


def disabled_message() -> str:
    """Return what to do to turn Pixabay on."""
    return (
        "Pixabay is off: set PIXABAY_API_KEY in .env "
        "(a free key at https://pixabay.com/api/docs/)"
    )


class PixabayClient:
    """Searches Pixabay for videos with the owner's API key."""

    name: StockSource = "pixabay"

    def __init__(
        self, api_key: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        if not api_key:
            raise ProviderDisabled(disabled_message())
        self._key = api_key
        self._transport = transport

    def search(
        self,
        query: str,
        *,
        orientation: str | None = None,
        min_duration_s: float = 0,
        per_page: int = 15,
    ) -> list[StockClip]:
        """Return the videos for query, at least min_duration_s long and of
        the orientation (the API has no such filter, so it is applied to the
        size of the chosen file), each with its best size (see best_file).
        Results are cached for 24 hours per query. Raises StockError."""
        per_page = max(MIN_PER_PAGE, min(per_page, MAX_PER_PAGE))
        key = (self._key, query, per_page)
        clips = cache.get(key)
        if clips is None:
            params: dict[str, str | int] = {
                "key": self._key,
                "q": query[:100],
                "per_page": per_page,
                "safesearch": "true",
            }
            with httpx.Client(transport=self._transport, timeout=TIMEOUT) as http:
                body = get_json(http, LABEL, SEARCH_URL, params=params)
            found = body.get("hits")
            hits = found if isinstance(found, list) else []
            clips = [clip for item in hits if (clip := _clip(item)) is not None]
            cache.put(key, clips)
        return [
            clip
            for clip in clips
            if clip.duration_s >= min_duration_s
            and (not orientation or _shape(clip) == orientation)
        ]


def _shape(clip: StockClip) -> str:
    """Return "landscape", "portrait" or "square" for the size of clip."""
    if clip.width == clip.height:
        return "square"
    return "landscape" if clip.width > clip.height else "portrait"


def _clip(item: Any) -> StockClip | None:
    """Return the StockClip of a Pixabay video hit, None if it has no
    usable file (a size can come with an empty url)."""
    if not isinstance(item, dict) or not item.get("id") or not item.get("pageURL"):
        return None
    sizes = [
        (int(v["width"]), int(v["height"]), v)
        for v in (item.get("videos") or {}).values()
        if isinstance(v, dict) and v.get("url") and v.get("width") and v.get("height")
    ]
    chosen = best_file(sizes)
    if chosen is None:
        return None
    creator = str(item.get("user") or "")
    page_url = str(item["pageURL"])
    profile = f"https://pixabay.com/users/{creator}-{item.get('user_id')}/"
    credit = f"Video by {creator} on Pixabay" if creator else "Video from Pixabay"
    return StockClip(
        provider="pixabay",
        provider_id=str(item["id"]),
        page_url=page_url,
        preview_url=chosen.get("thumbnail") or None,
        download_url=str(chosen["url"]),
        width=int(chosen["width"]),
        height=int(chosen["height"]),
        duration_s=float(item.get("duration") or 0),
        creator=creator,
        creator_url=profile if creator and item.get("user_id") else None,
        tags=[t.strip() for t in str(item.get("tags") or "").split(",") if t.strip()],
        license=LICENSE,
        attribution=f"{credit} ({page_url})",
    )
