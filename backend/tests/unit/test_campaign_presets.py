"""Tests for campaign presets: the length presets that cover a campaign's
range, the clip text that the campaign requires, applying a campaign to a
project and its clips (which then pass the rule checker), and new clips of a
campaign's project."""

from datetime import date
from typing import Any

import pytest
from clipforge import campaign_presets, campaigns
from clipforge.campaign_presets import (
    DESCRIPTION_MAX,
    apply_campaign,
    length_presets_for,
    preset_new_clips,
    preset_settings,
    preset_text,
)
from clipforge.campaign_rules import check_saved_clip
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import Campaign, CampaignCreate, ProcessingSettings
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session

CREDIT = "Credit: Creator (youtube.com/@creator)"


def campaign(**changes: Any) -> Campaign:
    fields: dict[str, Any] = {
        "id": 1,
        "name": "Creator clips",
        "permission_screenshot_asset_id": None,
        "permission_checked_at": None,
    }
    return Campaign.model_validate(fields | changes)


@pytest.mark.parametrize(
    ("low", "high", "presets"),
    [
        (15.0, 60.0, ["lt30", "30_60"]),
        (30.0, 60.0, ["30_60"]),
        (None, 25.0, ["lt30"]),
        (95.0, None, ["90_180", "180_300", "300_600", "600_900"]),
        (None, None, None),
        (1000.0, None, None),
    ],
)
def test_length_presets_cover_the_campaign_range(
    low: float | None, high: float | None, presets: list[str] | None
) -> None:
    assert length_presets_for(campaign(min_duration_s=low, max_duration_s=high)) == (
        presets
    )


def test_preset_settings_set_length_range_and_caption_template() -> None:
    settings = ProcessingSettings(length_presets=["60_90"], caption_template="neon")
    applied = campaign(
        min_duration_s=20.0, max_duration_s=45.0, caption_template="karaoke_bold"
    )

    changed = preset_settings(settings, applied)

    assert changed.length_presets == ["lt30", "30_60"]
    assert changed.caption_template == "karaoke_bold"
    assert preset_settings(settings, campaign()) == settings


def test_preset_text_puts_required_hashtags_first_and_appends_credit() -> None:
    applied = campaign(
        required_hashtags=["creator", "clips"],
        required_credit_line=CREDIT,
        required_tags_mentions=["@creator", "#ad"],
    )
    own = ["a", "b", "Clips", "c", "d", "e", "f", "g"]

    description, hashtags = preset_text("So good.", own, applied)

    assert hashtags == ["creator", "clips", "a", "b", "c", "d", "e", "f"]
    assert description == f"So good.\n\n{CREDIT}\n@creator #ad"


def test_preset_text_keeps_what_is_already_there() -> None:
    applied = campaign(required_credit_line=CREDIT, required_tags_mentions=["@me"])
    text = f"{CREDIT.upper()} hi @me"

    assert preset_text(text, ["x"], applied) == (text, ["x"])
    assert preset_text("", [], applied) == (f"{CREDIT}\n@me", [])


def test_preset_text_shortens_a_long_description_to_fit() -> None:
    applied = campaign(required_credit_line=CREDIT)

    description, _ = preset_text("word " * 80, [], applied)

    assert len(description) == DESCRIPTION_MAX
    assert description.endswith(f"…\n\n{CREDIT}")
    assert description.startswith("word word")


def add_campaign(engine: Engine, **fields: Any) -> int:
    body: dict[str, Any] = {
        "name": "Creator clips",
        "permission_source_url": "https://example.com/permission",
        "allowed_platforms": ["youtube"],
        "required_hashtags": ["creatorclips"],
        "required_credit_line": CREDIT,
        "required_tags_mentions": ["@creator"],
        "min_duration_s": 2.0,
        "max_duration_s": 30.0,
        "caption_template": "karaoke_bold",
    }
    created = campaigns.create_campaign(
        engine, CampaignCreate.model_validate(body | fields)
    )
    campaigns.set_permission_screenshot(engine, created.id, b"\x89PNG", ".png")
    return created.id


def test_applying_a_campaign_sets_the_project_and_its_clips(engine: Engine) -> None:
    campaign_id = add_campaign(engine)
    project_id = add_project(engine)
    clip_id = add_clip(engine, project_id, "candidate", 80, description="Wow.")
    with Session(engine) as session:
        row = session.get(ProjectRow, project_id)
        assert row is not None
        row.source_rights = "permission"
        session.add(row)
        session.commit()

    project = apply_campaign(engine, project_id, campaign_id)

    assert project.campaign_id == campaign_id
    assert project.settings.length_presets == ["lt30"]
    assert project.settings.caption_template == "karaoke_bold"
    assert project.credit_line == CREDIT
    with Session(engine) as session:
        clip = session.get(ClipRow, clip_id)
        assert clip is not None
        assert clip.description == f"Wow.\n\n{CREDIT}\n@creator"
        assert clip.hashtags[0] == "creatorclips"
    check = check_saved_clip(engine, clip_id, date(2026, 11, 1), "youtube")
    assert check.passed, check.results


def test_leaving_a_campaign_keeps_settings_and_clips(engine: Engine) -> None:
    campaign_id = add_campaign(engine)
    project_id = add_project(engine)
    applied = apply_campaign(engine, project_id, campaign_id)

    left = apply_campaign(engine, project_id, None)

    assert left.campaign_id is None
    assert left.settings == applied.settings
    assert left.credit_line == CREDIT


def test_applying_fails_without_changes_for_unknown_ids(engine: Engine) -> None:
    project_id = add_project(engine)

    with pytest.raises(campaigns.CampaignNotFound):
        apply_campaign(engine, project_id, 99)
    with pytest.raises(campaign_presets.ProjectNotFound):
        apply_campaign(engine, 99, None)
    with Session(engine) as session:
        row = session.get(ProjectRow, project_id)
        assert row is not None and row.campaign_id is None


def test_an_unknown_caption_template_is_refused(engine: Engine) -> None:
    campaign_id = add_campaign(engine, caption_template="gone")
    project_id = add_project(engine)

    with pytest.raises(campaign_presets.UnknownCaptionTemplate, match="'gone'"):
        apply_campaign(engine, project_id, campaign_id)


def test_new_clips_of_a_campaign_project_get_its_text(engine: Engine) -> None:
    campaign_id = add_campaign(engine, caption_template="neon")
    in_campaign = add_project(engine)
    apply_campaign(engine, in_campaign, campaign_id)
    plain = add_project(engine)
    new = add_clip(engine, in_campaign, "candidate", 80)
    other = add_clip(engine, plain, "candidate", 80)

    preset_new_clips(engine, in_campaign, [new])
    preset_new_clips(engine, plain, [other])

    with Session(engine) as session:
        new_row, other_row = session.get(ClipRow, new), session.get(ClipRow, other)
        assert new_row is not None and other_row is not None
        assert new_row.caption_template == "neon"
        assert new_row.description == f"{CREDIT}\n@creator"
        assert (other_row.caption_template, other_row.description) == (
            "karaoke_bold",
            "",
        )
