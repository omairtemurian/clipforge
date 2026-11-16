"""@handle to channel id (T28c; checked 2026-10-31 in
https://developers.google.com/youtube/v3/docs/channels/list,
docs/decisions.md TASK-195): channels.list with part=id and forHandle
costs 1 quota unit and needs an API key (YOUTUBE_API_KEY). The feed and
WebSub topic take only the "UC..." id, so a handle is resolved once, when
the channel is added.
"""

import re

import httpx

from clipforge.models import CHANNEL_ID_PATTERN

CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class HandleError(RuntimeError):
    """The handle could not be looked up; the message says why."""


class NeedsApiKey(HandleError):
    """No YouTube Data API key is configured."""


class HandleNotFound(HandleError):
    """No channel has the handle."""


def resolve_handle(
    handle: str, api_key: str, transport: httpx.BaseTransport | None = None
) -> str:
    """Return the "UC..." id of the channel with this @handle."""
    if not api_key:
        raise NeedsApiKey(
            "looking up an @handle needs YOUTUBE_API_KEY; paste the channel's"
            " /channel/UC... link instead"
        )
    params = {"part": "id", "forHandle": handle, "key": api_key}
    try:
        with httpx.Client(transport=transport, timeout=TIMEOUT) as http:
            response = http.get(CHANNELS_URL, params=params)
    except httpx.HTTPError as exc:
        raise HandleError(f"could not reach YouTube: {exc}") from exc
    if not response.is_success:
        raise HandleError(f"YouTube answered HTTP {response.status_code}")
    items = response.json().get("items") or []
    channel_id = str(items[0].get("id", "")) if items else ""
    if not channel_id:
        raise HandleNotFound(f"YouTube has no channel {handle}")
    if not re.fullmatch(CHANNEL_ID_PATTERN, channel_id):
        raise HandleError(f"YouTube answered an odd channel id for {handle}")
    return channel_id
