"""Tests for the campaign rule checker: each rule passes and fails, a project
without a campaign is only checked for its source rights, and a clip's
played length leaves out its cuts."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from builders import make_clip
from clipforge.campaign_rules import (
    check_clip,
    failed_message,
    has_hashtag,
    has_mention,
    played_length,
)
from clipforge.models import (
    Campaign,
    CampaignCheck,
    CampaignRule,
    Clip,
    ProcessingSettings,
    Project,
    RuleResult,
)

TODAY = date(2026, 11, 1)
CREDIT = "Clip of @creator's stream"


def campaign(**changes: Any) -> Campaign:
    """A complete active campaign that every compliant clip passes."""
    fields: dict[str, Any] = {
        "id": 3,
        "name": "Creator clips",
        "permission_source_url": "https://example.com/permission",
        "permission_screenshot_asset_id": 9,
        "permission_checked_at": datetime(2026, 10, 30, tzinfo=UTC),
        "allowed_platforms": ["youtube", "tiktok"],
        "required_hashtags": ["creatorclips"],
        "required_credit_line": CREDIT,
        "required_tags_mentions": ["@creator"],
        "min_duration_s": 2.0,
        "max_duration_s": 3.0,
    }
    return Campaign.model_validate(fields | changes)


def project(**changes: Any) -> Project:
    fields: dict[str, Any] = {
        "id": 1,
        "source_url": None,
        "source_path": "/videos/talk.mp4",
        "title": "talk",
        "duration": 60.0,
        "thumbnail_path": "",
        "settings": ProcessingSettings(),
        "status": "done",
        "created_at": datetime(2026, 10, 31, tzinfo=UTC),
        "source_rights": "permission",
        "campaign_id": 3,
    }
    return Project.model_validate(fields | changes)


def good_clip(**changes: Any) -> Clip:
    """A 2.5 s clip with the hashtag, credit line and mention."""
    fields: dict[str, Any] = {
        "description": f"He ate it all.\n\n{CREDIT}\n@creator",
        "hashtags": ["CreatorClips", "pizza"],
    }
    return make_clip("karaoke_bold", **(fields | changes))


def result(check: CampaignCheck, rule: CampaignRule) -> RuleResult:
    (found,) = [r for r in check.results if r.rule == rule]
    return found


def run(
    clip: Clip | None = None,
    the_project: Project | None = None,
    the_campaign: Campaign | None = None,
    platform: Any = "youtube",
    today: date = TODAY,
) -> CampaignCheck:
    return check_clip(
        clip or good_clip(),
        the_project or project(),
        the_campaign or campaign(),
        today,
        platform,
    )


def test_a_compliant_clip_passes_every_rule_in_order() -> None:
    check = run()

    assert check.passed
    assert [r.rule for r in check.results] == [
        "campaign_status",
        "permission",
        "source_rights",
        "min_duration",
        "max_duration",
        "hashtags",
        "credit_line",
        "mentions",
        "platform",
    ]
    assert (check.clip_id, check.campaign_id, check.platform) == (7, 3, "youtube")
    assert result(check, "min_duration").detail == "2.5s, at least 2s"


@pytest.mark.parametrize(
    ("changes", "today", "detail"),
    [
        ({"status": "paused"}, TODAY, "the campaign is paused"),
        ({"status": "ended"}, TODAY, "the campaign is ended"),
        ({"end_date": date(2026, 10, 31)}, TODAY, "the campaign ended on 2026-10-31"),
    ],
)
def test_campaign_status_fails_unless_active_and_not_past_its_end(
    changes: dict[str, Any], today: date, detail: str
) -> None:
    check = run(the_campaign=campaign(**changes), today=today)

    status = result(check, "campaign_status")
    assert (status.passed, status.detail) == (False, detail)
    assert not check.passed


def test_campaign_status_passes_on_its_last_day() -> None:
    status = result(run(the_campaign=campaign(end_date=TODAY)), "campaign_status")

    assert (status.passed, status.detail) == (
        True,
        "the campaign is active until 2026-11-01",
    )


def test_permission_fails_while_evidence_is_missing() -> None:
    lacking = campaign(permission_screenshot_asset_id=None, permission_checked_at=None)

    permission = result(run(the_campaign=lacking), "permission")

    assert not permission.passed
    assert permission.detail == (
        "add a screenshot of the permission, the date the permission was checked"
    )
    assert result(run(), "permission").passed


def test_source_rights_fail_while_unset() -> None:
    rights = result(run(the_project=project(source_rights=None)), "source_rights")

    assert (rights.passed, rights.detail) == (
        False,
        "choose the project's source rights",
    )
    assert result(run(), "source_rights").detail == "source rights: permission"


def test_a_project_without_campaign_is_only_checked_for_source_rights() -> None:
    plain = project(campaign_id=None, source_rights=None)

    check = check_clip(good_clip(hashtags=[]), plain, None, TODAY)

    assert check.campaign_id is None
    assert [(r.rule, r.passed) for r in check.results] == [("source_rights", False)]
    assert check_clip(good_clip(), project(), None, TODAY).passed


def test_min_duration_fails_for_a_shorter_clip_and_passes_at_the_minimum() -> None:
    short = result(run(the_campaign=campaign(min_duration_s=3.0)), "min_duration")
    exact = result(run(the_campaign=campaign(min_duration_s=2.5)), "min_duration")
    unset = result(run(the_campaign=campaign(min_duration_s=None)), "min_duration")

    assert (short.passed, short.detail) == (False, "the clip is 2.5s, under 3s")
    assert exact.passed
    assert (unset.passed, unset.detail) == (True, "no minimum length")


def test_max_duration_fails_for_a_longer_clip_and_passes_at_the_maximum() -> None:
    long = result(
        run(the_campaign=campaign(min_duration_s=1.0, max_duration_s=2.0)),
        "max_duration",
    )
    exact = result(run(the_campaign=campaign(max_duration_s=2.5)), "max_duration")
    unset = result(run(the_campaign=campaign(max_duration_s=None)), "max_duration")

    assert (long.passed, long.detail) == (False, "the clip is 2.5s, over 2s")
    assert exact.passed
    assert (unset.passed, unset.detail) == (True, "no maximum length")


def test_duration_counts_the_played_length_without_cuts() -> None:
    cut = good_clip(start=10.0, end=14.0, cut_ranges=[(11.0, 12.0)])

    assert played_length(cut) == 3.0
    assert result(run(clip=cut), "max_duration").passed
    assert not result(run(clip=good_clip(start=10.0, end=14.0)), "max_duration").passed


def test_played_length_sums_the_segments() -> None:
    clip = good_clip(segments=[(10.0, 11.5), (20.0, 21.25)], cut_ranges=[(20.0, 20.5)])

    assert played_length(clip) == 2.25


def test_hashtags_fail_until_each_required_one_is_there() -> None:
    lacking = campaign(required_hashtags=["creatorclips", "funny"])

    missing = result(run(the_campaign=lacking), "hashtags")
    in_text = result(
        run(
            clip=good_clip(description=f"So #Funny\n{CREDIT} @creator"),
            the_campaign=lacking,
        ),
        "hashtags",
    )

    assert (missing.passed, missing.detail) == (False, "add #funny")
    assert (in_text.passed, in_text.detail) == (True, "#creatorclips #funny")
    assert result(run(the_campaign=campaign(required_hashtags=[])), "hashtags").passed


def test_credit_line_fails_unless_the_description_holds_it() -> None:
    bare = good_clip(description="He ate it all. @creator")
    spaced = good_clip(description="clip   OF @creator's\nstream @creator")

    credit = result(run(clip=bare), "credit_line")

    assert (credit.passed, credit.detail) == (
        False,
        f'add "{CREDIT}" to the description',
    )
    assert result(run(clip=spaced), "credit_line").passed
    unset = result(run(the_campaign=campaign(required_credit_line="")), "credit_line")
    assert (unset.passed, unset.detail) == (True, "no credit line required")


def test_mentions_fail_unless_each_stands_alone_in_the_description() -> None:
    longer = good_clip(description="Thanks @creators and @creator_two")
    missing = result(run(clip=longer), "mentions")

    assert (missing.passed, missing.detail) == (
        False,
        "add @creator to the description",
    )
    upper = good_clip(description="Thanks @Creator!")
    assert result(run(clip=upper), "mentions").passed
    tag_in_list = campaign(required_tags_mentions=["#pizza"])
    assert result(run(the_campaign=tag_in_list), "mentions").passed


def test_platform_fails_unless_the_campaign_allows_it() -> None:
    denied = result(run(platform="instagram"), "platform")
    nothing = result(run(the_campaign=campaign(allowed_platforms=[])), "platform")
    any_platform = result(run(platform=None), "platform")

    assert (denied.passed, denied.detail) == (
        False,
        "the campaign allows youtube, tiktok, not instagram",
    )
    assert (nothing.passed, nothing.detail) == (
        False,
        "the campaign lists no allowed platform",
    )
    assert (any_platform.passed, any_platform.detail) == (
        True,
        "allowed: youtube, tiktok",
    )
    assert result(run(platform="tiktok"), "platform").detail == "tiktok is allowed"
    assert not result(run(platform="facebook"), "platform").passed


def test_failed_message_lists_each_failed_rule() -> None:
    check = run(platform="instagram", the_project=project(source_rights=None))

    assert failed_message(check) == (
        "clip 7 breaks campaign rules: choose the project's source rights; "
        "the campaign allows youtube, tiktok, not instagram"
    )


def test_matchers_need_whole_words() -> None:
    assert has_hashtag(["#Pizza"], "", "pizza")
    assert not has_hashtag([], "#pizzas tonight", "pizza")
    assert has_mention([], "thanks @creator.", "@creator")
    assert not has_mention([], "mail me@creator", "@creator")
