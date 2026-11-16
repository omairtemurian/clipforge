"""Tests of the always-included hashtags over the API (steering, owner
request 2026-11-02): the always_hashtags setting, an account's own, and
their place, with the campaign's required hashtags, in the AI post copy and
in the payload of a post that has no hashtags of its own."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from apihelpers import assert_error
from campaign_api import add, in_campaign
from clipforge import config
from clipforge.api.app import create_app
from fakes import FIXTURES, FakeLLMClient
from fastapi.testclient import TestClient
from post_api_fakes import make_drafts, rendered_clip
from seed import add_clip, add_work
from social_fakes import add_account
from sqlalchemy import Engine

FIRST = json.loads((FIXTURES / "post_copy" / "replies.json").read_text())["first"]
BULK = "/api/posts/bulk-schedule"
RULES = {
    "timezone": "Europe/Zurich",
    "times": ["09:00"],
    "posts_per_day": 1,
    "start_date": "2030-01-14",
}


@pytest.fixture
def env_file(work_in_tmp: Path) -> Path:
    """The .env.local that the Settings API writes."""
    return work_in_tmp / ".env.local"


@pytest.fixture
def ai_client(data_dir: Path) -> Iterator[TestClient]:
    """A client of an app whose LLM answers the post copy."""
    llm = FakeLLMClient(json.dumps(FIRST), repeat_last=True)
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        yield client


def engine_of(client: TestClient) -> Engine:
    engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
    return engine


def test_the_setting_is_saved_cleaned_and_read_back(
    client: TestClient, env_file: Path
) -> None:
    assert client.get("/api/settings").json()["always_hashtags"] == []

    response = client.put(
        "/api/settings", json={"always_hashtags": ["#MyBrand", " ad ", "AD", "#"]}
    )

    assert response.status_code == 200, response.text
    assert response.json()["always_hashtags"] == ["MyBrand", "ad"]
    assert config.settings.always_hashtags == ["MyBrand", "ad"]
    fresh = config.Settings(data_dir=config.settings.data_dir)
    assert fresh.always_hashtags == ["MyBrand", "ad"]
    cleared = client.put("/api/settings", json={"always_hashtags": []})
    assert cleared.json()["always_hashtags"] == []
    assert config.Settings(data_dir=config.settings.data_dir).always_hashtags == []


def test_the_setting_rejects_too_many_hashtags(client: TestClient) -> None:
    response = client.put(
        "/api/settings", json={"always_hashtags": [f"t{n}" for n in range(31)]}
    )

    assert response.status_code == 422


def test_an_accounts_hashtags_are_set_cleaned_and_listed(
    client: TestClient, api_engine: Engine
) -> None:
    account = add_account(api_engine, "main", "tiktok")
    assert client.get("/api/accounts").json()[0]["always_hashtags"] == []

    response = client.put(
        f"/api/accounts/{account}/hashtags", json={"always_hashtags": ["#Side", "side"]}
    )

    assert response.status_code == 200
    assert response.json()["always_hashtags"] == ["Side"]
    assert client.get("/api/accounts").json()[0]["always_hashtags"] == ["Side"]
    missing = client.put("/api/accounts/99/hashtags", json={"always_hashtags": []})
    assert_error(missing, 404, "not_found")


def clip_with_work(client: TestClient, campaign_tags: list[str]) -> int:
    """Add a clip with a transcript, in a project of a campaign that
    requires campaign_tags."""
    engine = engine_of(client)
    campaign = add(client, required_hashtags=campaign_tags)
    project_id = in_campaign(engine, campaign["id"])
    add_work(engine, project_id, FIXTURES / "sample.mp4")
    return add_clip(engine, project_id, "candidate", 80, "Pizza")


def test_the_copy_carries_the_setting_the_account_and_the_campaign(
    ai_client: TestClient,
) -> None:
    config.settings = config.Settings(
        data_dir=config.settings.data_dir, always_hashtags=["MyBrand"]
    )
    clip_id = clip_with_work(ai_client, ["Contest", "mybrand"])
    account = add_account(
        engine_of(ai_client), "main", "tiktok", always_hashtags=["Side"]
    )

    response = ai_client.post(
        f"/api/clips/{clip_id}/post-copy",
        json={"platform": "tiktok", "account_id": account},
    )

    assert response.status_code == 200, response.text
    assert response.json()["hashtags"] == [
        "MyBrand",
        "Side",
        "Contest",
        "yoga",
        "standup",
        "comedy",
        "FunnyMoments",
    ]


def test_a_rewrite_without_hashtags_keeps_them(ai_client: TestClient) -> None:
    config.settings = config.Settings(
        data_dir=config.settings.data_dir, always_hashtags=["MyBrand"]
    )
    clip_id = clip_with_work(ai_client, [])
    current = {"title": "", "caption": "Text.", "hashtags": ["old", "MyBrand"]}

    response = ai_client.post(
        f"/api/clips/{clip_id}/post-copy",
        json={"platform": "tiktok", "hashtags": "none", "current": current},
    )

    assert response.json() == {"title": "", "caption": "Text.", "hashtags": ["MyBrand"]}


def test_an_unknown_account_is_not_found(ai_client: TestClient) -> None:
    clip_id = clip_with_work(ai_client, [])

    response = ai_client.post(
        f"/api/clips/{clip_id}/post-copy", json={"platform": "tiktok", "account_id": 9}
    )

    assert_error(response, 404, "not_found")


def test_a_draft_without_hashtags_of_its_own_gets_the_required_ones(
    client: TestClient, api_engine: Engine
) -> None:
    config.settings = config.Settings(
        data_dir=config.settings.data_dir, always_hashtags=["MyBrand"]
    )
    clip_id = rendered_clip(api_engine)
    account = add_account(api_engine, "main", "tiktok", always_hashtags=["Side"])

    own = make_drafts(
        client,
        clip_id,
        [{"account_id": account, "text": {"hashtags": ["mine"]}}],
    )
    default = make_drafts(client, clip_id, [{"account_id": account, "text": {}}])

    assert own[0]["payload"]["caption"].endswith("#mine")
    assert default[0]["payload"]["caption"].endswith(
        "#MyBrand #Side #food #pizza #funny"
    )


def test_bulk_scheduled_posts_carry_the_required_hashtags(
    client: TestClient, api_engine: Engine
) -> None:
    config.settings = config.Settings(
        data_dir=config.settings.data_dir, always_hashtags=["MyBrand"]
    )
    clip_id = rendered_clip(api_engine)
    account = add_account(api_engine, "main", "youtube")
    body: dict[str, Any] = {
        "clip_ids": [clip_id],
        "targets": [{"account_id": account}],
        "rules": RULES,
    }

    response = client.post(BULK, json=body)

    assert response.status_code == 201, response.text
    payload = response.json()[0]["payload"]
    assert "#MyBrand" in payload["description"]
    assert "MyBrand" in payload["tags"]
