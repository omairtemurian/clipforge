"""Tests of GET/PUT /api/campaigns/{id}/autopilot (SPEC-v2 3.19): the
defaults, the hard cap of 5 posts a day (6 is a 422) and what a save
checks."""

from typing import Any

import pytest
from apihelpers import assert_error
from campaign_api import CAMPAIGNS, add
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from submission_fakes import account

RULES = {"timezone": "Europe/Zurich", "times": ["09:00", "18:00"]}


def url(campaign_id: int) -> str:
    return f"{CAMPAIGNS}/{campaign_id}/autopilot"


def test_a_campaign_starts_with_the_defaults(client: TestClient) -> None:
    campaign = add(client)

    body = client.get(url(campaign["id"])).json()

    assert body == {
        "campaign_id": campaign["id"],
        "enabled": False,
        "max_clips_per_source": 3,
        "slots": None,
        "max_posts_per_day": 3,
        "draft_ttl_days": 3,
        "account_ids": [],
        "min_clip_s": None,
        "max_clip_s": None,
        "caption_template": None,
        "brand_template_id": None,
        "proedit_enabled": False,
        "proedit_preset": "clean_pro",
        "proedit_max_intensity": "standard",
    }


def test_settings_are_saved_and_read_back(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client)
    youtube = account(api_engine, "youtube")

    response = client.put(
        url(campaign["id"]),
        json={
            "enabled": True,
            "max_posts_per_day": 5,
            "draft_ttl_days": 2,
            "slots": RULES,
            "account_ids": [youtube],
        },
    )

    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["enabled"] is True
    assert (saved["max_posts_per_day"], saved["draft_ttl_days"]) == (5, 2)
    assert saved["account_ids"] == [youtube]
    assert client.get(url(campaign["id"])).json() == saved


def test_six_posts_a_day_is_a_422_and_nothing_changes(client: TestClient) -> None:
    campaign = add(client)

    response = client.put(url(campaign["id"]), json={"max_posts_per_day": 6})

    assert_error(response, 422, "validation_error")
    assert client.get(url(campaign["id"])).json()["max_posts_per_day"] == 3


@pytest.mark.parametrize(
    "body",
    [
        {"draft_ttl_days": 0},
        {"max_clips_per_source": 11},
        {"min_clip_s": 60, "max_clip_s": 30},
        {"slots": RULES, "max_posts_per_day": 1},
        {"extra": True},
    ],
)
def test_settings_out_of_range_are_a_422(
    client: TestClient, body: dict[str, Any]
) -> None:
    campaign = add(client)

    assert_error(client.put(url(campaign["id"]), json=body), 422, "validation_error")


def test_a_save_is_checked_against_what_it_names(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client, allowed_platforms=["youtube"])
    tiktok = account(api_engine, "tiktok")
    path = url(campaign["id"])

    assert_error(client.put(path, json={"account_ids": [404]}), 404, "not_found")
    assert_error(client.put(path, json={"brand_template_id": 404}), 404, "not_found")
    assert_error(
        client.put(path, json={"account_ids": [tiktok]}), 422, "validation_error"
    )
    assert_error(
        client.put(path, json={"caption_template": "nope"}), 422, "validation_error"
    )


def test_an_unknown_campaign_is_a_404(client: TestClient) -> None:
    assert_error(client.get(url(404)), 404, "not_found")
    assert_error(client.put(url(404), json={}), 404, "not_found")
