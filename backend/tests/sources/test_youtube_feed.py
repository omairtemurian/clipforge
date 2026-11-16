"""Tests for the YouTube channel feed (clipforge.sources.youtube_feed): the
recorded feed parsed, the feed URL, and the 404 / HTTP error / network
error / not-a-feed answers. respx answers instead of YouTube."""

from datetime import UTC, datetime

import httpx
import pytest
import respx
from clipforge.sources.youtube_feed import (
    FeedError,
    Validators,
    feed_url,
    fetch_feed,
    parse_feed,
)
from youtube_fakes import (
    CHANNEL,
    FEED_FIXTURES,
    MIDDLE,
    NEWEST,
    OLDEST,
    feed_response,
    feed_route,
)


def test_the_feed_url_names_the_channel_id() -> None:
    assert feed_url(CHANNEL) == (
        f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL}"
    )


def test_the_recorded_feed_is_parsed_newest_first() -> None:
    feed = parse_feed((FEED_FIXTURES / "feed_after.xml").read_bytes())

    assert feed.title == "YouTube"
    assert [e.video_id for e in feed.entries] == [NEWEST, MIDDLE, OLDEST]
    newest = feed.entries[0]
    assert newest.title == (
        "not every pumpkin was built for the afterlife @evanandkatelynextras"
    )
    assert newest.published == datetime(2026, 10, 31, 14, 0, 33, tzinfo=UTC)
    assert newest.url == f"https://www.youtube.com/watch?v={NEWEST}"


def test_entries_without_a_video_id_or_date_are_handled() -> None:
    xml = b"""<feed xmlns="http://www.w3.org/2005/Atom"
        xmlns:yt="http://www.youtube.com/xml/schemas/2015">
      <entry><title>no id</title></entry>
      <entry><yt:videoId>abc</yt:videoId><published>soon</published></entry>
    </feed>"""
    feed = parse_feed(xml)

    assert feed.title == ""
    assert [(e.video_id, e.title, e.published) for e in feed.entries] == [
        ("abc", "", None)
    ]


@pytest.mark.parametrize(
    "xml",
    [b"<html>sign in</html>", b"<feed", b""],
    ids=["not-atom", "broken", "empty"],
)
def test_an_answer_that_is_not_a_feed_raises(xml: bytes) -> None:
    with pytest.raises(FeedError, match="not"):
        parse_feed(xml)


def test_fetch_reads_the_feed(respx_mock: respx.MockRouter) -> None:
    route = feed_route(respx_mock, "feed_before")

    result = fetch_feed(CHANNEL)

    assert result.feed is not None
    assert [e.video_id for e in result.feed.entries] == [MIDDLE, OLDEST]
    assert result.validators == Validators()
    assert route.call_count == 1
    assert "if-none-match" not in route.calls.last.request.headers


def test_fetch_sends_the_validators_and_reads_304_as_unchanged(
    respx_mock: respx.MockRouter,
) -> None:
    tagged = feed_response("feed_before")
    tagged.headers["ETag"] = '"v1"'
    tagged.headers["Last-Modified"] = "Sat, 31 Oct 2026 10:00:00 GMT"
    route = feed_route(respx_mock, tagged, httpx.Response(304))

    first = fetch_feed(CHANNEL)
    second = fetch_feed(CHANNEL, validators=first.validators)

    assert first.validators == Validators(
        etag='"v1"', last_modified="Sat, 31 Oct 2026 10:00:00 GMT"
    )
    sent = route.calls.last.request.headers
    assert sent["if-none-match"] == '"v1"'
    assert sent["if-modified-since"] == "Sat, 31 Oct 2026 10:00:00 GMT"
    assert second.feed is None and second.validators == first.validators


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (httpx.Response(404, text="Not Found"), "no channel"),
        (httpx.Response(500), "HTTP 500"),
        (httpx.ConnectError("offline"), "could not read"),
        (httpx.Response(200, content=b"x" * 2_000_001), "too large"),
    ],
    ids=["unknown-channel", "server-error", "offline", "too-large"],
)
def test_fetch_errors_raise_feed_error(
    respx_mock: respx.MockRouter, answer: httpx.Response | Exception, message: str
) -> None:
    feed_route(respx_mock, answer)

    with pytest.raises(FeedError, match=message):
        fetch_feed(CHANNEL)
