"""Tests for the bulk scheduler endpoint (POST /posts/bulk-schedule): every
clip on every account in its next free slot, around posts already there,
drafts for agents and queued posts for the owner only."""

from typing import Any

import pytest
from apihelpers import assert_error
from clipforge import config, posts
from clipforge.post_schedule import daily_cap
from fastapi.testclient import TestClient
from post_api_fakes import AGENT, accounts, make_drafts, rendered_clip
from sqlalchemy import Engine

BULK = "/api/posts/bulk-schedule"
# Monday 2030-01-14; 09:00 and 18:00 in Zurich are 08:00Z and 17:00Z.
RULES = {
    "timezone": "Europe/Zurich",
    "times": ["09:00", "18:00"],
    "posts_per_day": 1,
    "skip_days": ["sat", "sun"],
    "start_date": "2030-01-14",
}


@pytest.fixture
def clip_ids(api_engine: Engine) -> list[int]:
    return [rendered_clip(api_engine, "One"), rendered_clip(api_engine, "Two")]


def body(clip_ids: list[int], *account_ids: int, **changes: Any) -> dict[str, Any]:
    targets = [{"account_id": account_id} for account_id in account_ids]
    return {"clip_ids": clip_ids, "targets": targets, "rules": RULES} | changes


def times(created: list[dict[str, Any]]) -> list[tuple[int, int, str]]:
    return [(p["clip_id"], p["account_id"], p["scheduled_at"]) for p in created]


def test_bulk_schedule_fills_each_accounts_next_slots(
    client: TestClient, api_engine: Engine, clip_ids: list[int]
) -> None:
    youtube, instagram = accounts(api_engine, "youtube", "instagram")
    one, two = clip_ids
    make_drafts(
        client,
        one,
        [{"account_id": youtube}],
        scheduled_at="2030-01-14T08:00:00Z",
    )

    response = client.post(BULK, json=body(clip_ids, youtube, instagram), headers=AGENT)

    assert response.status_code == 201, response.text
    created = response.json()
    assert times(created) == [
        (one, instagram, "2030-01-14T08:00:00Z"),
        (one, youtube, "2030-01-15T08:00:00Z"),
        (two, instagram, "2030-01-15T08:00:00Z"),
        (two, youtube, "2030-01-16T08:00:00Z"),
    ]
    assert {p["status"] for p in created} == {"draft"}
    assert created[0]["payload"]["caption"].startswith("One")


def test_bulk_schedule_skips_the_skip_days(
    client: TestClient, api_engine: Engine
) -> None:
    clip_ids = [rendered_clip(api_engine, f"Clip {n}") for n in range(5)]
    (youtube,) = accounts(api_engine, "youtube")

    created = client.post(BULK, json=body(clip_ids, youtube)).json()

    assert [p["scheduled_at"][:10] for p in created] == [
        "2030-01-14",
        "2030-01-15",
        "2030-01-16",
        "2030-01-17",
        "2030-01-18",
    ]
    assert "2030-01-21" not in {p["scheduled_at"][:10] for p in created}


def test_owner_queues_a_bulk_schedule(
    client: TestClient, api_engine: Engine, clip_ids: list[int]
) -> None:
    (youtube,) = accounts(api_engine, "youtube")

    agent = client.post(BULK, json=body(clip_ids, youtube, queue=True), headers=AGENT)
    owner = client.post(BULK, json=body(clip_ids, youtube, queue=True))

    assert_error(agent, 403, "human_only")
    assert [p["status"] for p in owner.json()] == ["queued", "queued"]


def test_a_refused_bulk_schedule_saves_nothing(
    client: TestClient, api_engine: Engine, clip_ids: list[int]
) -> None:
    youtube, tiktok = accounts(api_engine, "youtube", "tiktok")

    not_ready = client.post(BULK, json=body(clip_ids, youtube, tiktok, queue=True))
    bad_text = body(clip_ids, youtube)
    bad_text["targets"][0]["text"] = {"collaborators": ["chef"]}
    refused = client.post(BULK, json=bad_text)
    twice = client.post(BULK, json=body(clip_ids, youtube, youtube))
    unknown = client.post(BULK, json=body(clip_ids, 99))

    assert_error(not_ready, 409, "post_not_ready")
    assert_error(refused, 422, "validation_error")
    assert_error(twice, 422, "validation_error")
    assert_error(unknown, 404, "not_found")
    assert posts.list_posts(api_engine) == []


def test_daily_caps_follow_the_platforms_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.settings, "youtube_daily_uploads", 4)

    assert [daily_cap(p) for p in ("youtube", "tiktok", "instagram", "facebook")] == [
        4,
        15,
        100,
        30,
    ]
    assert daily_cap("x") is None
