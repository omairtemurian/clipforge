"""Tests that the Campaign model has the fields of SPEC-v2 3.18 (plus
end_date and the preset's caption_template), tidies what the owner types
and reports whether the permission evidence is complete."""

from datetime import UTC, datetime
from typing import Any

import pytest
from clipforge.models import Campaign, CampaignCreate, CampaignPatch
from pydantic import ValidationError

SPEC_FIELDS = (
    "id name creator_name source_channel_urls platform_board campaign_url "
    "permission_source_url permission_screenshot_asset_id permission_checked_at "
    "badge rate_per_1k_usd budget_note allowed_platforms required_hashtags "
    "required_credit_line required_tags_mentions min_duration_s max_duration_s "
    "banned_content_notes monetization_allowed_elsewhere submission_instructions "
    "status notes"
).split()
URL = "https://example.com/permission"
NOW = datetime(2026, 10, 31, tzinfo=UTC)


def campaign(**changes: Any) -> Campaign:
    base: dict[str, Any] = {
        "id": 1,
        "name": "Clips",
        "permission_source_url": URL,
        "permission_screenshot_asset_id": 7,
        "permission_checked_at": NOW,
    }
    return Campaign.model_validate(base | changes)


def test_campaign_has_the_spec_fields_end_date_and_caption_template() -> None:
    assert set(Campaign.model_fields) == {
        *SPEC_FIELDS,
        "end_date",
        "caption_template",
        "allow_heavy_edits",
    }


def test_hashtags_lose_their_hash_and_mentions_and_hashtags_are_unique() -> None:
    made = campaign(
        required_hashtags=["#Clips", "clips", " #  ", "#fun"],
        required_tags_mentions=["@Afro", "@afro", "", "@"],
        allowed_platforms=["tiktok", "youtube", "tiktok"],
    )

    assert made.required_hashtags == ["Clips", "fun"]
    assert made.required_tags_mentions == ["@Afro"]
    assert made.allowed_platforms == ["tiktok", "youtube"]


@pytest.mark.parametrize(
    ("changes", "complete"),
    [
        ({}, True),
        ({"permission_source_url": None}, False),
        ({"permission_screenshot_asset_id": None}, False),
        ({"permission_checked_at": None}, False),
    ],
)
def test_permission_complete_needs_url_screenshot_and_date(
    changes: dict[str, Any], complete: bool
) -> None:
    made = campaign(**changes)

    assert made.permission_complete is complete
    assert made.model_dump()["permission_complete"] is complete


def test_a_patch_needs_a_field_and_forbids_server_set_fields() -> None:
    assert CampaignPatch(notes="x").model_fields_set == {"notes"}
    for bad in ({}, {"id": 1}, {"permission_checked_at": NOW}):
        with pytest.raises(ValidationError):
            CampaignPatch.model_validate(bad)


def test_equal_minimum_and_maximum_durations_are_valid() -> None:
    CampaignCreate(name="C", min_duration_s=30, max_duration_s=30)
