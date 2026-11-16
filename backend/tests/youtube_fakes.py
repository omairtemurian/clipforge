"""Recorded YouTube channel feeds for the Auto Import tests (tests only).

fixtures/youtube_feed/feed_after.xml is the feed of YouTube's own channel
as https://www.youtube.com/feeds/videos.xml?channel_id=UCBR8-60-B28hp2BmDPdntcQ
answered on 2026-10-31, cut to its 3 newest entries; feed_before.xml is the
same without the newest entry (the feed one upload earlier) and
feed_empty.xml has no entry (a channel without videos).
"""

from pathlib import Path

import httpx
import respx
from clipforge.sources.youtube_feed import FEED_URL

FEED_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "youtube_feed"
CHANNEL = "UCBR8-60-B28hp2BmDPdntcQ"
# The entries of feed_after.xml, newest first.
NEWEST, MIDDLE, OLDEST = "86Ccatsw92c", "etcRgjG4qRo", "iJWdJsDuEjA"


def feed_response(name: str, status: int = 200) -> httpx.Response:
    """The recorded feed fixtures/youtube_feed/<name>.xml as YouTube sends it."""
    return httpx.Response(
        status,
        content=(FEED_FIXTURES / f"{name}.xml").read_bytes(),
        headers={"content-type": "text/xml; charset=UTF-8"},
    )


def feed_route(
    respx_mock: respx.MockRouter,
    *answers: str | httpx.Response | Exception,
    channel: str = CHANNEL,
) -> respx.Route:
    """Answer the channel's feed requests in order: a fixture name or a
    response or an
    exception to raise each."""
    return respx_mock.get(FEED_URL, params={"channel_id": channel}).mock(
        side_effect=[feed_response(a) if isinstance(a, str) else a for a in answers]
    )
