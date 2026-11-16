"""Pexels stock videos (SPEC-v2 3.6; endpoints, auth header and license
checked 2026-11-02 in https://www.pexels.com/api/documentation/ and
https://www.pexels.com/license/, docs/decisions.md TASK-119).

GET https://api.pexels.com/v1/videos/search with the key alone in the
`Authorization` header (no "Bearer"); the default limit is 200 requests an
hour and 20,000 a month. The license allows free, commercial use and
editing without attribution; the API terms ask for a visible link to Pexels
and credit to the videographer, so the attribution is kept and shown.
"""

from typing import Any

import httpx

from clipforge.models import StockClip, StockSource
from clipforge.stock.base import (
    TIMEOUT,
    ProviderDisabled,
    best_file,
    get_json,
)

LABEL = "Pexels"
SEARCH_URL = "https://api.pexels.com/v1/videos/search"
LICENSE = "Pexels License"
MAX_PER_PAGE = 80


def disabled_message() -> str:
    """Return what to do to turn Pexels on."""
    return (
        "Pexels is off: set PEXELS_API_KEY in .env "
        "(a free key at https://www.pexels.com/api/)"
    )


class PexelsClient:
    """Searches Pexels for videos with the owner's API key."""

    name: StockSource = "pexels"

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
        """Return the videos for query, at least min_duration_s long, each
        with its best mp4 file (see best_file). Raises StockError."""
        params: dict[str, str | int] = {
            "query": query,
            "per_page": min(per_page, MAX_PER_PAGE),
        }
        if orientation:
            params["orientation"] = orientation
        with httpx.Client(transport=self._transport, timeout=TIMEOUT) as http:
            body = get_json(
                http,
                LABEL,
                SEARCH_URL,
                params=params,
                headers={"Authorization": self._key},
            )
        found = body.get("videos")
        videos = found if isinstance(found, list) else []
        clips = [clip for item in videos if (clip := _clip(item)) is not None]
        return [clip for clip in clips if clip.duration_s >= min_duration_s]


def _clip(item: Any) -> StockClip | None:
    """Return the StockClip of a Pexels video object, None if it has no
    usable mp4 file."""
    if not isinstance(item, dict):
        return None
    files = [
        (int(f["width"]), int(f["height"]), f)
        for f in item.get("video_files") or []
        if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")
    ]
    chosen = best_file(files)
    if chosen is None or not item.get("id") or not item.get("url"):
        return None
    user = item.get("user") or {}
    creator = str(user.get("name") or "")
    page_url = str(item["url"])
    credit = f"Video by {creator} on Pexels" if creator else "Video from Pexels"
    return StockClip(
        provider="pexels",
        provider_id=str(item["id"]),
        page_url=page_url,
        preview_url=item.get("image") or None,
        download_url=str(chosen["link"]),
        width=int(chosen["width"]),
        height=int(chosen["height"]),
        duration_s=float(item.get("duration") or 0),
        creator=creator,
        creator_url=user.get("url") or None,
        tags=[],
        license=LICENSE,
        attribution=f"{credit} ({page_url})",
    )
