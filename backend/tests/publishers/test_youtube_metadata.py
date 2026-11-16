"""Tests for the YouTube video resource of a post
(clipforge.publishers.youtube_metadata): defaults from the clip, YouTube's
title, description and tag limits, and publishAt for scheduled posts."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from builders import make_clip
from clipforge.models import YouTubePostOptions
from clipforge.publishers.base import PublishError
from clipforge.publishers.youtube_metadata import fit_tags, options_of, video_resource

NOW = datetime(2026, 11, 1, 7, 30, tzinfo=UTC)
CLIP = make_clip("bold", title="Pizza <night>", description="Best slice ever.")


def resource(
    payload: dict[str, Any], scheduled_at: datetime | None = None
) -> dict[str, Any]:
    """Return the video resource of payload for CLIP."""
    return video_resource(options_of(payload), CLIP, scheduled_at, NOW)


def test_defaults_come_from_the_clip() -> None:
    assert resource({}) == {
        "snippet": {
            "title": "Pizza night",
            "description": "Best slice ever.\n\n#food #pizza #funny",
            "categoryId": "22",
            "tags": ["food", "pizza", "funny"],
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": False,
        },
    }


def test_a_scheduled_public_post_goes_up_private_with_publish_at() -> None:
    later = datetime(2026, 11, 3, 17, 0, tzinfo=UTC)

    status = resource({"privacy": "public"}, later)["status"]

    assert status["privacyStatus"] == "private"
    assert status["publishAt"] == "2026-11-03T17:00:00Z"


@pytest.mark.parametrize(
    ("privacy", "scheduled_at"),
    [
        ("public", NOW - timedelta(minutes=1)),
        ("public", None),
        ("unlisted", NOW + timedelta(days=1)),
        ("private", NOW + timedelta(days=1)),
    ],
)
def test_publish_at_only_for_future_public_posts(
    privacy: str, scheduled_at: datetime | None
) -> None:
    status = resource({"privacy": privacy}, scheduled_at)["status"]

    assert status["privacyStatus"] == privacy
    assert "publishAt" not in status


def test_a_naive_schedule_is_utc() -> None:
    naive = datetime(2026, 11, 2, 9, 15)

    assert resource({}, naive)["status"]["publishAt"] == "2026-11-02T09:15:00Z"


def test_title_and_description_fit_youtube_limits() -> None:
    snippet = resource({"title": "t" * 96 + "<>x ", "description": "é" * 3000})[
        "snippet"
    ]

    assert snippet["title"] == "t" * 96 + "x"
    assert snippet["description"] == "é" * 2500
    assert len(snippet["description"].encode()) == 5000


def test_a_long_clip_title_is_cut_to_100_characters() -> None:
    clip = make_clip("bold", title="word " * 30)

    title = video_resource(options_of({}), clip, None, NOW)["snippet"]["title"]

    assert title == ("word " * 20).strip()


def test_a_title_cannot_be_empty() -> None:
    with pytest.raises(PublishError, match="needs a title"):
        resource({"title": "<>"})


def test_invalid_settings_name_their_fields() -> None:
    with pytest.raises(PublishError) as failed:
        resource({"privacy": "friends", "category_id": "music", "title": "x" * 101})

    assert failed.value.message == (
        "The YouTube post settings are invalid: title, category_id, privacy."
    )
    assert not failed.value.retryable


def test_unknown_payload_keys_are_ignored() -> None:
    assert options_of({"caption": "for TikTok"}) == YouTubePostOptions()


def test_tags_are_cleaned_and_kept_under_500_characters() -> None:
    assert fit_tags(["#Food", "food", " ", "deep  dish", "<b>"]) == [
        "Food",
        "deep dish",
        "b",
    ]
    # 50 tags of 9 characters and their commas take 499 characters.
    tags = [f"tag{n:06d}" for n in range(60)]
    kept = fit_tags(tags)
    assert len(kept) == 50
    assert len(",".join(kept)) == 499
    # A tag with a space counts 2 more (as if quoted).
    assert fit_tags(["a" * 496, "b c"]) == ["a" * 496]
    assert fit_tags(["a" * 494, "b c"]) == ["a" * 494, "b c"]
