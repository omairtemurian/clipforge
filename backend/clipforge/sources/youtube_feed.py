"""A YouTube channel's public RSS (Atom) feed: its 15 latest videos.

The feed is https://www.youtube.com/feeds/videos.xml?channel_id=<UC...>
(checked 2026-10-31, docs/decisions.md TASK-70): text/xml, newest entry
first, 404 for an unknown channel, no ETag. Each <entry> has <yt:videoId>,
<title>, <published> and a <link rel="alternate"> (a /watch or /shorts
page). fetch_feed sends the validators of the previous answer
(If-None-Match / If-Modified-Since) when it had any, so a server that
starts sending them can answer 304: the feed did not change
(FeedResult.feed is None). The same Atom shape is what the WebSub hub
pushes (watch/websub). The stdlib parser is used: its Expat (>= 2.7.2
here) refuses entity expansion attacks and never loads external entities.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

import httpx

FEED_URL = "https://www.youtube.com/feeds/videos.xml"
WATCH_URL = "https://www.youtube.com/watch"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
# A feed is about 20 KB; a bigger answer is not a channel feed.
MAX_FEED_BYTES = 2_000_000
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


class FeedError(RuntimeError):
    """The feed could not be read; the message says why."""


@dataclass(frozen=True)
class FeedEntry:
    """A video of the feed; published is None if the feed has no date."""

    video_id: str
    title: str
    published: datetime | None

    @property
    def url(self) -> str:
        """The video's watch page, the source of its project."""
        return f"{WATCH_URL}?{urlencode({'v': self.video_id})}"


@dataclass(frozen=True)
class Feed:
    """A channel's title and its videos, newest first (the feed's order)."""

    title: str
    entries: list[FeedEntry]


def feed_url(channel_id: str) -> str:
    """Return the RSS feed URL of the channel with this "UC..." id."""
    return f"{FEED_URL}?{urlencode({'channel_id': channel_id})}"


@dataclass(frozen=True)
class Validators:
    """The ETag and Last-Modified of a feed answer (empty: none sent)."""

    etag: str = ""
    last_modified: str = ""

    def headers(self) -> dict[str, str]:
        """The conditional request headers that these validators give."""
        headers = {}
        if self.etag:
            headers["If-None-Match"] = self.etag
        if self.last_modified:
            headers["If-Modified-Since"] = self.last_modified
        return headers


@dataclass(frozen=True)
class FeedResult:
    """A feed read: the feed (None if unchanged, HTTP 304) and the
    validators to send with the next read."""

    feed: Feed | None
    validators: Validators


def fetch_feed(
    channel_id: str,
    transport: httpx.BaseTransport | None = None,
    validators: Validators | None = None,
) -> FeedResult:
    """Download and parse the channel's feed, conditionally if validators
    are given. Raises FeedError for a network error, a channel that does not
    exist (404), another HTTP error or an answer that is not a feed."""
    sent = validators or Validators()
    try:
        with httpx.Client(
            transport=transport, timeout=TIMEOUT, follow_redirects=True
        ) as http:
            response = http.get(feed_url(channel_id), headers=sent.headers())
    except httpx.HTTPError as exc:
        raise FeedError(f"could not read the channel feed: {exc}") from exc
    if response.status_code == 304:
        return FeedResult(None, sent)
    if response.status_code == 404:
        raise FeedError(f"YouTube has no channel {channel_id} (feed 404)")
    if response.status_code != 200:
        raise FeedError(f"the channel feed answered HTTP {response.status_code}")
    if len(response.content) > MAX_FEED_BYTES:
        raise FeedError("the channel feed is too large")
    received = Validators(
        etag=response.headers.get("etag", ""),
        last_modified=response.headers.get("last-modified", ""),
    )
    return FeedResult(parse_feed(response.content), received)


def parse_feed(xml: bytes) -> Feed:
    """Parse a channel feed; entries without a video id are skipped. Raises
    FeedError if xml is not an Atom feed."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise FeedError(f"the channel feed is not valid XML: {exc}") from exc
    if root.tag != f"{{{NS['atom']}}}feed":
        raise FeedError("the channel feed is not an Atom feed")
    entries = []
    for node in root.findall("atom:entry", NS):
        video_id = _text(node, "yt:videoId")
        if video_id:
            entries.append(
                FeedEntry(
                    video_id=video_id,
                    title=_text(node, "atom:title"),
                    published=_datetime(_text(node, "atom:published")),
                )
            )
    return Feed(title=_text(root, "atom:title"), entries=entries)


def _text(node: ET.Element, path: str) -> str:
    return (node.findtext(path, default="", namespaces=NS) or "").strip()


def _datetime(value: str) -> datetime | None:
    """Parse an RFC 3339 date of the feed; None if it is missing or bad."""
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None
