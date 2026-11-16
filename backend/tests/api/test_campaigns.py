"""Tests for the campaign endpoints (api/campaigns.py): create, list, get,
change and delete a campaign
(the screenshot and the permission guard are in test_campaign_permission_api)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from apihelpers import assert_error
from campaign_api import CAMPAIGNS, PERMISSION_URL, add, upload
from fastapi.testclient import TestClient

FULL = {
    "name": "Afro Nation clips",
    "creator_name": "Afro Nation",
    "source_channel_urls": ["https://www.youtube.com/@AfroNation"],
    "platform_board": "whop",
    "campaign_url": "https://example.com/campaign/1",
    "permission_source_url": PERMISSION_URL,
    "badge": "paid",
    "rate_per_1k_usd": 0.5,
    "budget_note": "$2000 budget",
    "allowed_platforms": ["youtube", "tiktok"],
    "required_hashtags": ["#afronation", "clips"],
    "required_credit_line": "Credit: Afro Nation",
    "required_tags_mentions": ["@afronation"],
    "min_duration_s": 15,
    "max_duration_s": 60,
    "banned_content_notes": "No music",
    "monetization_allowed_elsewhere": False,
    "submission_instructions": "Paste the link",
    "status": "paused",
    "notes": "Ask on Discord",
    "end_date": "2026-12-31",
}


def test_a_campaign_is_created_with_every_field_and_listed(client: TestClient) -> None:
    assert client.get(CAMPAIGNS).json() == []

    campaign = add(client, **FULL)

    assert {k: v for k, v in campaign.items() if k in FULL} == FULL | {
        "required_hashtags": ["afronation", "clips"]
    }
    assert campaign["id"] == 1
    assert campaign["permission_screenshot_asset_id"] is None
    assert campaign["permission_complete"] is False
    assert client.get(CAMPAIGNS).json() == [campaign]
    assert client.get(f"{CAMPAIGNS}/{campaign['id']}").json() == campaign


def test_a_campaign_needs_only_a_name_and_gets_defaults(client: TestClient) -> None:
    campaign = add(client)

    assert campaign["platform_board"] == "other"
    assert campaign["badge"] == "open"
    assert campaign["status"] == "active"
    assert campaign["rate_per_1k_usd"] is None
    assert campaign["monetization_allowed_elsewhere"] is None
    assert campaign["end_date"] is None
    assert campaign["allowed_platforms"] == []
    assert campaign["permission_source_url"] is None
    assert campaign["permission_checked_at"] is None


def test_the_permission_date_is_set_when_the_source_url_is_saved(
    client: TestClient,
) -> None:
    before = datetime.now(UTC) - timedelta(seconds=1)

    campaign = add(client, permission_source_url=PERMISSION_URL)

    checked = datetime.fromisoformat(campaign["permission_checked_at"])
    assert before <= checked <= datetime.now(UTC)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": "  "},
        {"name": "x" * 201},
        {"name": "C", "platform_board": "discord"},
        {"name": "C", "badge": "vip"},
        {"name": "C", "status": "done"},
        {"name": "C", "allowed_platforms": ["myspace"]},
        {"name": "C", "rate_per_1k_usd": -1},
        {"name": "C", "min_duration_s": 0},
        {"name": "C", "min_duration_s": 60, "max_duration_s": 15},
        {"name": "C", "campaign_url": "ftp://example.com"},
        {"name": "C", "permission_source_url": "not a url"},
        {"name": "C", "source_channel_urls": ["nope"]},
        {"name": "C", "end_date": "tomorrow"},
        {"name": "C", "required_credit_line": "x" * 201},
        {"name": "C", "monetization_allowed_elsewhere": "maybe"},
    ],
)
def test_an_invalid_campaign_is_rejected(
    client: TestClient, body: dict[str, Any]
) -> None:
    assert_error(client.post(CAMPAIGNS, json=body), 422, "validation_error")
    assert client.get(CAMPAIGNS).json() == []


def test_a_patch_changes_only_the_fields_sent(client: TestClient) -> None:
    created = add(client, **FULL)

    response = client.patch(
        f"{CAMPAIGNS}/{created['id']}",
        json={"status": "active", "rate_per_1k_usd": None, "end_date": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["rate_per_1k_usd"], body["end_date"]) == (
        "active",
        None,
        None,
    )
    unchanged = {"name", "creator_name", "badge", "required_hashtags", "notes"}
    assert all(body[k] == created[k] for k in unchanged)
    assert body["permission_checked_at"] == created["permission_checked_at"]


def test_a_new_source_url_sets_the_date_again_and_clearing_it_clears_it(
    client: TestClient,
) -> None:
    created = add(client, permission_source_url=PERMISSION_URL)
    url = f"{CAMPAIGNS}/{created['id']}"

    changed = client.patch(
        url, json={"permission_source_url": PERMISSION_URL + "?v=2"}
    ).json()
    cleared = client.patch(url, json={"permission_source_url": None}).json()

    assert changed["permission_checked_at"] >= created["permission_checked_at"]
    assert cleared["permission_source_url"] is None
    assert cleared["permission_checked_at"] is None


def test_a_patch_that_would_make_the_durations_invalid_changes_nothing(
    client: TestClient,
) -> None:
    created = add(client, min_duration_s=15, max_duration_s=60)
    url = f"{CAMPAIGNS}/{created['id']}"

    assert_error(
        client.patch(url, json={"max_duration_s": 10, "name": "New"}),
        422,
        "validation_error",
    )

    assert client.get(url).json() == created


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": ""},
        {"id": 5},
        {"permission_checked_at": "2026-01-01T00:00:00Z"},
        {"permission_screenshot_asset_id": 1},
        {"status": "gone"},
    ],
)
def test_an_invalid_patch_is_rejected(client: TestClient, body: dict[str, Any]) -> None:
    created = add(client)

    response = client.patch(f"{CAMPAIGNS}/{created['id']}", json=body)

    assert_error(response, 422, "validation_error")
    assert client.get(f"{CAMPAIGNS}/{created['id']}").json() == created


def test_an_unknown_campaign_is_404(client: TestClient) -> None:
    url = f"{CAMPAIGNS}/99"

    assert_error(client.get(url), 404, "not_found")
    assert_error(client.patch(url, json={"notes": "x"}), 404, "not_found")
    assert_error(client.delete(url), 404, "not_found")
    assert_error(upload(client, 99), 404, "not_found")
    assert_error(client.get(f"{url}/permission-screenshot"), 404, "not_found")
