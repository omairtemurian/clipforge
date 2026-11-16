"""Tests for the YouTube publisher's daily quota guard
(clipforge.publishers.quota with the youtube buckets), its thumbnail step
and its channel lookup (fetch_account), against recorded answers (respx)."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from clipforge import config, posts, usage
from clipforge.models import Post
from clipforge.oauth_tokens import Token
from clipforge.publishers import youtube
from clipforge.publishers.base import PublishError, Upload
from clipforge.publishers.publish import publish_post
from clipforge.publishers.youtube_upload import UPLOAD_URL
from clipforge.token_store import TokenStore
from social_fakes import clip_of
from sqlalchemy import Engine
from youtube_publish_fakes import (
    ACCESS,
    CHANNEL_ID,
    NOW,
    SESSION_URL,
    VIDEO_ID,
    answer,
    make_publisher,
    queue_youtube_post,
    session_started,
    units_used,
    write_sized_video,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def seed_usage(engine: Engine, kind: str, units: float, at: datetime) -> None:
    """Record units of kind at the given time."""
    usage.record(engine, kind, units, at=at)


def upload_with_thumbnail(
    engine: Engine, clip_id: int, store: TokenStore, thumbnail: Path
) -> str:
    """Upload the clip with a thumbnail straight through the publisher
    (metered like the publish run) and return the video id."""
    post_id = queue_youtube_post(engine, clip_id, store)
    post: Post = posts.get_post(engine, post_id)
    clip = clip_of(engine, clip_id)
    assert clip.output_path is not None
    publisher = make_publisher()
    upload = Upload(post, clip, Path(clip.output_path), thumbnail)
    with usage.recording(engine, clip.project_id):
        session = publisher.session(store, f"ref-{CHANNEL_ID}")
        return publisher.upload(session, upload).external_post_id


@pytest.fixture
def uploads_ok(respx_mock: respx.MockRouter) -> respx.MockRouter:
    """YouTube takes the video in one go."""
    respx_mock.post(UPLOAD_URL).mock(return_value=session_started())
    respx_mock.put(SESSION_URL).mock(return_value=answer(201, "video_uploaded"))
    return respx_mock


def test_thumbnail_is_set_after_the_upload(
    engine: Engine, clip_id: int, store: TokenStore, uploads_ok: respx.MockRouter
) -> None:
    write_sized_video(engine, clip_id, 1000)
    thumbnail = Path(clip_of(engine, clip_id).output_path or "").with_suffix(".png")
    thumbnail.write_bytes(PNG)
    route = uploads_ok.post(youtube.THUMBNAIL_URL).mock(
        return_value=answer(200, "thumbnail_set")
    )

    assert upload_with_thumbnail(engine, clip_id, store, thumbnail) == VIDEO_ID

    request = route.calls.last.request
    assert dict(request.url.params) == {"videoId": VIDEO_ID, "uploadType": "media"}
    assert request.headers["content-type"] == "image/png"
    assert request.content == PNG
    assert units_used(engine, "youtube_uploads") == 1
    assert units_used(engine, "youtube_quota_units") == 50


def test_a_failed_thumbnail_keeps_the_video(
    engine: Engine, clip_id: int, store: TokenStore, uploads_ok: respx.MockRouter
) -> None:
    write_sized_video(engine, clip_id, 1000)
    thumbnail = Path(clip_of(engine, clip_id).output_path or "").with_suffix(".jpg")
    thumbnail.write_bytes(b"\xff\xd8\xff")
    uploads_ok.post(youtube.THUMBNAIL_URL).mock(
        return_value=answer(429, "error_rate_limit")
    )

    assert upload_with_thumbnail(engine, clip_id, store, thumbnail) == VIDEO_ID


def test_thumbnail_is_skipped_when_the_units_are_used_up(
    engine: Engine, clip_id: int, store: TokenStore, uploads_ok: respx.MockRouter
) -> None:
    write_sized_video(engine, clip_id, 1000)
    thumbnail = Path(clip_of(engine, clip_id).output_path or "").with_suffix(".png")
    thumbnail.write_bytes(PNG)
    seed_usage(engine, "youtube_quota_units", 9_960, NOW)
    route = uploads_ok.post(youtube.THUMBNAIL_URL)

    assert upload_with_thumbnail(engine, clip_id, store, thumbnail) == VIDEO_ID
    assert not route.called
    assert units_used(engine, "youtube_quota_units") == 9_960


def test_the_daily_upload_quota_holds_posts_back(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.settings, "youtube_daily_uploads", 3)
    write_sized_video(engine, clip_id, 1000)
    post_id = queue_youtube_post(engine, clip_id, store)
    seed_usage(engine, "youtube_uploads", 3, datetime(2026, 11, 1, 7, 0, tzinfo=UTC))

    post = publish_post(engine, post_id, store, lambda _p: make_publisher())

    assert post.status == "queued"
    assert post.error == (
        "The daily YouTube upload (videos.insert) quota is used up (3 of 3); "
        "it resets at midnight America/Los_Angeles time."
    )
    assert not respx_mock.calls
    assert units_used(engine, "youtube_uploads") == 3


def test_the_quota_day_starts_at_midnight_pacific(engine: Engine) -> None:
    # 2026-11-01 00:00 PDT is 07:00 UTC; the day before ended at 06:59.
    assert youtube.UPLOADS.day_start(NOW) == datetime(2026, 11, 1, 7, tzinfo=UTC)
    seed_usage(engine, "youtube_uploads", 99, datetime(2026, 11, 1, 6, 59, tzinfo=UTC))
    seed_usage(engine, "youtube_uploads", 1, datetime(2026, 11, 1, 7, 1, tzinfo=UTC))
    # The next day starts at 08:00 UTC: 1 November has 25 hours (PST).
    seed_usage(engine, "youtube_uploads", 5, datetime(2026, 11, 2, 7, 30, tzinfo=UTC))
    seed_usage(engine, "youtube_uploads", 7, datetime(2026, 11, 2, 8, 0, tzinfo=UTC))

    assert youtube.UPLOADS.used(engine, NOW) == 6
    with usage.recording(engine, None):
        youtube.UPLOADS.spend(1, NOW)
    assert youtube.UPLOADS.used(engine, NOW) == 7


def test_quota_is_not_metered_outside_a_recording(engine: Engine) -> None:
    youtube.UNITS.spend(10_001, NOW)

    assert units_used(engine, "youtube_quota_units") == 0


def test_fetch_account_names_the_channel_and_its_restrictions(
    engine: Engine, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(youtube.CHANNELS_URL).mock(
        return_value=answer(200, "channels_mine")
    )

    with usage.recording(engine, None):
        profile = make_publisher().fetch_account(Token(access_token=ACCESS))

    assert (profile.external_id, profile.display_name) == (CHANNEL_ID, "Clip Lab")
    assert profile.restrictions[0].startswith(
        "Daily limits of your Google Cloud project: 100 uploads and 10000"
    )
    assert profile.restrictions[1] == youtube.UNAUDITED
    assert "long uploads: eligible" in profile.restrictions[2]
    request = route.calls.last.request
    assert dict(request.url.params) == {"part": "snippet,status", "mine": "true"}
    assert request.headers["authorization"] == f"Bearer {ACCESS}"
    assert units_used(engine, "youtube_quota_units") == 1


@pytest.mark.parametrize(
    ("answered", "text"),
    [
        (answer(200, "channels_none"), "has no YouTube channel"),
        (answer(403, "error_quota"), "quotaExceeded"),
    ],
)
def test_fetch_account_failures(
    respx_mock: respx.MockRouter, answered: httpx.Response, text: str
) -> None:
    respx_mock.get(youtube.CHANNELS_URL).mock(return_value=answered)

    with pytest.raises(PublishError) as failed:
        make_publisher().fetch_account(Token(access_token=ACCESS))

    assert text in failed.value.message


def test_chunks_must_be_whole_256_kib_units() -> None:
    client = make_publisher().client
    with pytest.raises(ValueError, match="256 KiB"):
        youtube.YouTubePublisher(client, chunk_bytes=1000)
