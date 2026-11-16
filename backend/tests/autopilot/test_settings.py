"""Tests of the autopilot settings (clipforge.autopilot.settings, SPEC-v2
3.19): the defaults, the limits (5 posts a day at most), what a save checks
and what the rows of the drafts and the feedback keep."""

from datetime import UTC, datetime
from typing import Any

import pytest
from clipforge import campaign_accounts, campaigns, social_accounts
from clipforge.autopilot import settings
from clipforge.autopilot.rows import DraftRow, FeedbackEventRow
from clipforge.campaign_presets import UnknownCaptionTemplate
from clipforge.db import BrandTemplateRow
from clipforge.models import AutopilotSettingsUpdate
from pydantic import ValidationError
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session, select
from submission_fakes import account, new_campaign

RULES: dict[str, Any] = {"timezone": "Europe/Zurich", "times": ["09:00", "18:00"]}


def update(**fields: Any) -> AutopilotSettingsUpdate:
    return AutopilotSettingsUpdate.model_validate(fields)


def test_a_campaign_that_was_never_set_up_has_the_defaults(engine: Engine) -> None:
    campaign = new_campaign(engine)

    saved = settings.get_settings(engine, campaign.id)

    assert saved.campaign_id == campaign.id
    assert saved.enabled is False
    assert saved.max_clips_per_source == 3
    assert saved.max_posts_per_day == 3
    assert saved.draft_ttl_days == 3
    assert saved.slots is None
    assert saved.account_ids == []
    assert (saved.min_clip_s, saved.max_clip_s) == (None, None)
    assert (saved.caption_template, saved.brand_template_id) == (None, None)


def test_an_unknown_campaign_has_no_settings(engine: Engine) -> None:
    with pytest.raises(campaigns.CampaignNotFound):
        settings.get_settings(engine, 99)
    with pytest.raises(campaigns.CampaignNotFound):
        settings.save_settings(engine, 99, update())


@pytest.mark.parametrize("posts", [1, 3, 5])
def test_posts_a_day_up_to_the_hard_cap_of_5_are_accepted(posts: int) -> None:
    assert update(max_posts_per_day=posts).max_posts_per_day == posts


@pytest.mark.parametrize("posts", [6, 0, -1])
def test_more_than_5_posts_a_day_is_refused(posts: int) -> None:
    with pytest.raises(ValidationError, match="max_posts_per_day"):
        update(max_posts_per_day=posts)


@pytest.mark.parametrize(
    "fields",
    [
        {"max_clips_per_source": 0},
        {"max_clips_per_source": 11},
        {"draft_ttl_days": 0},
        {"draft_ttl_days": 31},
        {"min_clip_s": 0},
        {"min_clip_s": 90, "max_clip_s": 30},
        {"slots": RULES, "max_posts_per_day": 1},
        {"slots": RULES | {"posts_per_day": 3}},
        {"unknown": 1},
    ],
)
def test_settings_out_of_range_are_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        update(**fields)


def test_slots_may_fit_the_daily_limit() -> None:
    kept = update(slots=RULES | {"posts_per_day": 1}, max_posts_per_day=1)
    assert kept.slots is not None
    assert len(kept.slots.daily_times()) == 1
    assert update(slots=RULES).slots is not None


def test_saved_settings_are_read_back_and_replace_the_ones_before(
    engine: Engine,
) -> None:
    campaign = new_campaign(engine)
    youtube, tiktok = account(engine, "youtube"), account(engine, "tiktok")

    saved = settings.save_settings(
        engine,
        campaign.id,
        update(
            enabled=True,
            max_clips_per_source=5,
            slots=RULES,
            max_posts_per_day=4,
            draft_ttl_days=7,
            account_ids=[tiktok, youtube, tiktok],
            min_clip_s=20,
            max_clip_s=60,
            caption_template="boxed",
        ),
    )

    assert settings.get_settings(engine, campaign.id) == saved
    assert saved.enabled is True
    assert (saved.max_clips_per_source, saved.max_posts_per_day) == (5, 4)
    assert saved.draft_ttl_days == 7
    assert saved.account_ids == [tiktok, youtube]
    assert saved.slots is not None
    assert [t.isoformat() for t in saved.slots.times] == ["09:00:00", "18:00:00"]
    assert (saved.min_clip_s, saved.max_clip_s) == (20, 60)
    assert saved.caption_template == "boxed"

    again = settings.save_settings(engine, campaign.id, update(enabled=False))
    assert again.enabled is False
    assert again.slots is None
    assert again.account_ids == []
    assert again.max_posts_per_day == 3


def test_each_campaign_has_its_own_settings(engine: Engine) -> None:
    first, second = new_campaign(engine), new_campaign(engine, name="Second")

    settings.save_settings(engine, first.id, update(enabled=True))

    assert settings.get_settings(engine, second.id).enabled is False


def test_an_unknown_caption_template_is_refused_and_nothing_changes(
    engine: Engine,
) -> None:
    campaign = new_campaign(engine)

    with pytest.raises(UnknownCaptionTemplate):
        settings.save_settings(
            engine, campaign.id, update(enabled=True, caption_template="nope")
        )

    assert settings.get_settings(engine, campaign.id).enabled is False


def test_an_unknown_account_or_brand_template_is_refused(engine: Engine) -> None:
    campaign = new_campaign(engine)

    with pytest.raises(social_accounts.AccountNotFound):
        settings.save_settings(engine, campaign.id, update(account_ids=[404]))
    with pytest.raises(settings.BrandTemplateNotFound):
        settings.save_settings(engine, campaign.id, update(brand_template_id=404))

    assert settings.get_settings(engine, campaign.id).account_ids == []


def test_an_account_on_a_platform_the_campaign_does_not_allow_is_refused(
    engine: Engine,
) -> None:
    campaign = new_campaign(engine, allowed_platforms=["youtube"])
    tiktok = account(engine, "tiktok")

    with pytest.raises(campaign_accounts.PlatformNotAllowed):
        settings.save_settings(engine, campaign.id, update(account_ids=[tiktok]))
    youtube = account(engine, "youtube")
    saved = settings.save_settings(engine, campaign.id, update(account_ids=[youtube]))
    assert saved.account_ids == [youtube]


def test_a_brand_template_is_kept_until_it_is_deleted(engine: Engine) -> None:
    campaign = new_campaign(engine)
    with Session(engine) as session:
        brand = BrandTemplateRow(
            name="Pizza",
            logo_path="logo.png",
            logo_position="top_right",
            logo_opacity=1.0,
            font="Inter",
            primary_color="#ff0000",
        )
        session.add(brand)
        session.commit()
        brand_id = brand.id
    assert brand_id is not None
    settings.save_settings(engine, campaign.id, update(brand_template_id=brand_id))

    with Session(engine) as session:
        session.delete(session.get(BrandTemplateRow, brand_id))
        session.commit()

    assert settings.get_settings(engine, campaign.id).brand_template_id is None


def test_a_disconnected_account_drops_out_of_the_settings(engine: Engine) -> None:
    campaign = new_campaign(engine)
    youtube, tiktok = account(engine, "youtube"), account(engine, "tiktok")
    settings.save_settings(engine, campaign.id, update(account_ids=[youtube, tiktok]))

    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM social_account WHERE id = {youtube}")

    assert settings.get_settings(engine, campaign.id).account_ids == [tiktok]


def test_deleting_a_campaign_removes_its_settings(engine: Engine, rows: Any) -> None:
    campaign = new_campaign(engine)
    settings.save_settings(engine, campaign.id, update(enabled=True))

    campaigns.delete_campaign(engine, campaign.id)

    assert rows("SELECT * FROM autopilot_settings") == []


def test_a_draft_keeps_its_rule_results_and_times_in_utc(engine: Engine) -> None:
    campaign = new_campaign(engine)
    clip_id = add_clip(engine, add_project(engine), "candidate", 70)
    results = [{"rule": "min_duration", "passed": False, "detail": "too short"}]

    with Session(engine) as session:
        session.add(
            DraftRow(
                clip_id=clip_id,
                campaign_id=campaign.id,
                status="needs_fix",
                rule_results=results,  # type: ignore[arg-type]
            )
        )
        session.commit()
    with Session(engine) as session:
        draft = session.exec(select(DraftRow)).one().to_model()

    assert draft.status == "needs_fix"
    assert [(r.rule, r.passed) for r in draft.rule_results] == [("min_duration", False)]
    assert draft.reject_reason is None
    assert draft.decided_at is None
    assert draft.created_at.tzinfo is UTC
    assert abs(datetime.now(UTC) - draft.created_at).total_seconds() < 60


def test_feedback_stays_when_its_clip_is_deleted(engine: Engine, rows: Any) -> None:
    campaign = new_campaign(engine)
    clip_id = add_clip(engine, add_project(engine), "candidate", 70)
    with Session(engine) as session:
        session.add(
            FeedbackEventRow(
                clip_id=clip_id,
                campaign_id=campaign.id,
                action="rejected",
                reason="too_long",
            )
        )
        session.commit()

    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM clip WHERE id = {clip_id}")

    with Session(engine) as session:
        event = session.exec(select(FeedbackEventRow)).one().to_model()
    assert (event.clip_id, event.action, event.reason) == (None, "rejected", "too_long")
    assert event.at.tzinfo is UTC
