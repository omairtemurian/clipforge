"""Tests for the post endpoints (clipforge.api.posts): drafts with
per-platform text, edit / reschedule / cancel only in draft or queued, and
the owner-only queue and publish (agents with an API key get 403)."""

import pytest
from apihelpers import assert_error
from clipforge import posts
from fastapi.testclient import TestClient
from post_api_fakes import (
    AGENT,
    LATER,
    accounts,
    make_draft,
    make_drafts,
    rendered_clip,
)
from sqlalchemy import Engine


@pytest.fixture
def clip_id(api_engine: Engine) -> int:
    return rendered_clip(api_engine)


def test_drafts_get_each_platforms_payload(
    client: TestClient, api_engine: Engine, clip_id: int
) -> None:
    youtube, tiktok = accounts(api_engine, "youtube", "tiktok")
    targets = [
        {"account_id": youtube, "text": {"title": "Best bite", "privacy": "unlisted"}},
        {"account_id": tiktok, "text": {"caption": "Hot", "hashtags": ["fyp"]}},
    ]

    drafts = make_drafts(client, clip_id, targets, scheduled_at=LATER)

    assert [(d["platform"], d["status"]) for d in drafts] == [
        ("youtube", "draft"),
        ("tiktok", "draft"),
    ]
    assert drafts[0]["payload"]["title"] == "Best bite"
    assert drafts[0]["payload"]["privacy"] == "unlisted"
    assert drafts[1]["payload"]["caption"] == "Pizza night\n\nHot\n\n#fyp"
    assert {d["scheduled_at"] for d in drafts} == {"2030-01-15T09:00:00Z"}
    listed = client.get("/api/posts", params={"clip_id": clip_id, "status": "draft"})
    assert [p["id"] for p in listed.json()] == [d["id"] for d in drafts]


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"targets": [{"account_id": 99}]}, 404, "not_found"),
        (
            {"targets": [{"account_id": 0, "text": {"collaborators": ["chef"]}}]},
            422,
            "validation_error",
        ),
        ({"targets": [{"account_id": 0}, {"account_id": 0}]}, 422, "validation_error"),
        (
            {"targets": [{"account_id": 0}], "scheduled_at": "2001-01-01T00:00:00Z"},
            422,
            "validation_error",
        ),
        (
            {"targets": [{"account_id": 0}], "thumbnail_asset_id": 77},
            422,
            "validation_error",
        ),
    ],
)
def test_bad_drafts_are_refused(
    client: TestClient,
    api_engine: Engine,
    clip_id: int,
    body: dict[str, object],
    status: int,
    code: str,
) -> None:
    (youtube,) = accounts(api_engine, "youtube")
    for target in body["targets"]:  # type: ignore[attr-defined]
        if target["account_id"] == 0:
            target["account_id"] = youtube

    response = client.post(f"/api/clips/{clip_id}/posts", json=body)

    assert_error(response, status, code)
    assert posts.list_posts(api_engine) == []


def test_unknown_clip_is_404(client: TestClient) -> None:
    response = client.post(
        "/api/clips/999/posts", json={"targets": [{"account_id": 1}]}
    )

    assert_error(response, 404, "not_found")


def test_agents_make_drafts_and_draft_schedules(
    client: TestClient, api_engine: Engine, clip_id: int
) -> None:
    (youtube,) = accounts(api_engine, "youtube")
    target = {"account_id": youtube, "text": {}}

    created = client.post(
        f"/api/clips/{clip_id}/posts", json={"targets": [target]}, headers=AGENT
    )
    post_id = created.json()[0]["id"]
    moved = client.patch(
        f"/api/posts/{post_id}",
        json={"scheduled_at": LATER, "text": {"title": "Agent title"}},
        headers=AGENT,
    )

    assert created.status_code == 201
    assert moved.status_code == 200
    assert moved.json()["status"] == "draft"
    assert moved.json()["scheduled_at"] == "2030-01-15T09:00:00Z"
    assert moved.json()["payload"]["title"] == "Agent title"


@pytest.mark.parametrize("headers", [AGENT, {"Authorization": "Bearer cf_agent_key"}])
def test_agents_cannot_queue_or_publish(
    client: TestClient, api_engine: Engine, clip_id: int, headers: dict[str, str]
) -> None:
    (youtube,) = accounts(api_engine, "youtube")
    post_id = make_draft(client, clip_id, youtube)

    queued = client.post(f"/api/posts/{post_id}/queue", json={}, headers=headers)
    published = client.post(f"/api/posts/{post_id}/publish", headers=headers)

    assert_error(queued, 403, "human_only")
    assert_error(published, 403, "human_only")
    assert posts.get_post(api_engine, post_id).status == "draft"


def test_agents_cannot_change_a_queued_post(
    client: TestClient, api_engine: Engine, clip_id: int
) -> None:
    (youtube,) = accounts(api_engine, "youtube")
    post_id = make_draft(client, clip_id, youtube)
    client.post(f"/api/posts/{post_id}/queue", json={"scheduled_at": LATER})

    response = client.patch(
        f"/api/posts/{post_id}", json={"scheduled_at": None}, headers=AGENT
    )

    assert_error(response, 403, "human_only")


def test_owner_queues_reschedules_and_cancels(
    client: TestClient, api_engine: Engine, clip_id: int
) -> None:
    (youtube,) = accounts(api_engine, "youtube")
    post_id = make_draft(client, clip_id, youtube)

    queued = client.post(f"/api/posts/{post_id}/queue", json={"scheduled_at": LATER})
    moved = client.patch(
        f"/api/posts/{post_id}", json={"scheduled_at": "2030-02-01T18:30:00+01:00"}
    )
    canceled = client.post(f"/api/posts/{post_id}/cancel")

    assert (queued.json()["status"], queued.json()["scheduled_at"]) == (
        "queued",
        "2030-01-15T09:00:00Z",
    )
    assert moved.json()["scheduled_at"] == "2030-02-01T17:30:00Z"
    assert canceled.json()["status"] == "canceled"


@pytest.mark.parametrize("status", ["uploading", "published", "failed", "canceled"])
def test_only_draft_and_queued_posts_change(
    client: TestClient, api_engine: Engine, clip_id: int, status: str
) -> None:
    (youtube,) = accounts(api_engine, "youtube")
    post_id = make_draft(client, clip_id, youtube)
    path = {"uploading": ["queued", "uploading"], "published": ["queued", "uploading"]}
    path |= {"failed": ["queued", "uploading"], "canceled": []}
    for step in [*path[status], status]:
        if posts.get_post(api_engine, post_id).status != step:
            posts.move(api_engine, post_id, step)  # type: ignore[arg-type]

    rescheduled = client.patch(f"/api/posts/{post_id}", json={"scheduled_at": LATER})
    canceled = client.post(f"/api/posts/{post_id}/cancel")

    assert_error(rescheduled, 409, "post_locked")
    assert_error(canceled, 409, "post_locked")
    assert posts.get_post(api_engine, post_id).status == status


def test_missing_post_is_404(client: TestClient) -> None:
    assert_error(client.get("/api/posts/5"), 404, "not_found")
    assert_error(client.post("/api/posts/5/cancel"), 404, "not_found")
