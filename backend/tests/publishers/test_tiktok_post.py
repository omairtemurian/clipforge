"""Tests for a TikTok Direct Post's settings (clipforge.publishers.tiktok_post)
and the upload's chunk plan (clipforge.publishers.tiktok_api.chunk_plan):
pure helpers, no HTTP."""

import pytest
from builders import make_clip
from clipforge.models import TikTokPostOptions
from clipforge.publishers.base import PublishError
from clipforge.publishers.tiktok_api import chunk_plan
from clipforge.publishers.tiktok_post import (
    CreatorInfo,
    failure,
    fit_utf16,
    options_of,
    post_info,
    result_of,
)

MIB = 1024 * 1024
CREATOR = CreatorInfo(
    username="cliplab",
    nickname="Clip Lab",
    privacy_options=("PUBLIC_TO_EVERYONE", "SELF_ONLY"),
    comment_disabled=False,
    duet_disabled=True,
    stitch_disabled=False,
    max_duration_s=600,
)


@pytest.mark.parametrize(
    ("size", "plan"),
    [
        (3 * MIB, (3 * MIB, 1)),
        (10 * MIB, (10 * MIB, 1)),
        (25 * MIB + 7, (10 * MIB, 2)),
        (50 * MIB, (10 * MIB, 5)),
    ],
)
def test_chunk_plan_follows_the_media_transfer_rules(
    size: int, plan: tuple[int, int]
) -> None:
    assert chunk_plan(size, 10 * MIB) == plan


def test_fit_utf16_counts_emoji_as_two_units() -> None:
    assert fit_utf16("abc", 3) == "abc"
    assert fit_utf16("ab\U0001f600", 3) == "ab"
    assert fit_utf16("ab\U0001f600", 4) == "ab\U0001f600"
    assert fit_utf16("one two", 4) == "one"


def test_the_default_caption_is_the_title_and_hashtags() -> None:
    clip = make_clip("karaoke_bold", title=" Big news ", hashtags=["#ai", "clips", "#"])
    options = TikTokPostOptions(privacy_level="SELF_ONLY", allow_comment=True)

    info = post_info(options, clip, CREATOR)

    assert info == {
        "title": "Big news\n\n#ai #clips",
        "privacy_level": "SELF_ONLY",
        "disable_comment": False,
        "disable_duet": True,
        "disable_stitch": True,
        "brand_content_toggle": False,
        "brand_organic_toggle": False,
        "is_aigc": False,
    }


def test_a_caption_and_cover_frame_are_sent_as_given() -> None:
    clip = make_clip("karaoke_bold", title="Ignored")
    options = TikTokPostOptions(
        caption="x" * 2300,
        privacy_level="PUBLIC_TO_EVERYONE",
        allow_duet=True,
        cover_timestamp_ms=1500,
    )

    info = post_info(options, clip, CREATOR)

    assert len(info["title"]) == 2200
    assert info["disable_duet"] is True
    assert info["video_cover_timestamp_ms"] == 1500


def test_options_need_a_privacy_level_and_valid_fields() -> None:
    with pytest.raises(PublishError, match="privacy level") as missing:
        options_of({"caption": "hi"})
    with pytest.raises(PublishError, match="invalid") as invalid:
        options_of({"privacy_level": "SELF_ONLY", "branded_content": True})

    assert not missing.value.retryable and not invalid.value.retryable


def test_creator_restrictions_list_what_the_account_allows() -> None:
    creator = CreatorInfo.of(
        {
            "creator_username": "cliplab",
            "privacy_level_options": ["FOLLOWER_OF_CREATOR", "SELF_ONLY"],
            "comment_disabled": True,
            "max_video_post_duration_sec": 60,
        }
    )

    assert creator.restrictions() == [
        "The TikTok account is private.",
        "Who can see posts of this account: followers, only me.",
        "Longest video this account can post: 60 s.",
        "The account turned off comments.",
    ]
    assert CreatorInfo.of({}).restrictions() == []


def test_the_result_links_a_public_post_only() -> None:
    public = result_of("pub-1", {"publicaly_available_post_id": [42]}, "cliplab")
    private = result_of("pub-1", {"publicaly_available_post_id": []}, "cliplab")

    assert (public.external_post_id, public.url) == (
        "42",
        "https://www.tiktok.com/@cliplab/video/42",
    )
    assert (private.external_post_id, private.url) == ("pub-1", None)


def test_a_failed_status_is_retryable_only_when_it_may_pass() -> None:
    assert failure("internal").retryable
    assert failure("spam_risk_too_many_posts").retryable
    banned = failure("spam_risk_user_banned_from_posting")
    assert not banned.retryable
    assert "banned the account" in str(banned)
