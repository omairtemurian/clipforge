"""Tests for the campaign preset and rule check endpoints: applying a campaign
to a project, the pass/fail of each rule for a clip, and publishing blocked
with 409 and the failed rules while one fails."""

from typing import Any

from apihelpers import assert_error
from campaign_api import (
    CAMPAIGNS,
    PERMISSION_URL,
    add,
    rules_publish_app,
    upload,
)
from clipforge.db import ProjectRow
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session

CREDIT = "Clip of the Creator stream"
RULES: dict[str, Any] = {
    "permission_source_url": PERMISSION_URL,
    "allowed_platforms": ["youtube"],
    "required_hashtags": ["creatorclips"],
    "required_credit_line": CREDIT,
    "required_tags_mentions": ["@creator"],
    "min_duration_s": 2.0,
    "max_duration_s": 30.0,
    "caption_template": "neon",
}


def project_with_clip(engine: Engine, rights: Any = "permission") -> tuple[int, int]:
    """Add a project with source rights and a 2.5 s clip; return their ids."""
    project_id = add_project(engine)
    with Session(engine) as session:
        row = session.get(ProjectRow, project_id)
        assert row is not None
        row.source_rights = rights
        session.add(row)
        session.commit()
    return project_id, add_clip(engine, project_id, "candidate", 80)


def ready_campaign(client: TestClient, **changes: Any) -> int:
    campaign = add(client, **(RULES | changes))
    assert upload(client, campaign["id"]).status_code == 200
    return int(campaign["id"])


def test_put_campaign_applies_its_preset(
    client: TestClient, api_engine: Engine
) -> None:
    campaign_id = ready_campaign(client)
    project_id, clip_id = project_with_clip(api_engine)

    response = client.put(
        f"/api/projects/{project_id}/campaign", json={"campaign_id": campaign_id}
    )

    assert response.status_code == 200
    project = response.json()
    assert project["campaign_id"] == campaign_id
    assert project["credit_line"] == CREDIT
    assert project["settings"]["length_presets"] == ["lt30"]
    assert project["settings"]["caption_template"] == "neon"
    clip = client.get(f"/api/clips/{clip_id}").json()
    assert clip["caption_template"] == "neon"
    assert clip["hashtags"][0] == "creatorclips"
    assert clip["description"].endswith(f"{CREDIT}\n@creator")


def test_put_campaign_errors(client: TestClient, api_engine: Engine) -> None:
    project_id, _ = project_with_clip(api_engine)
    url = f"/api/projects/{project_id}/campaign"

    assert_error(client.put(url, json={"campaign_id": 99}), 422, "validation_error")
    assert_error(client.put(url, json={}), 422, "validation_error")
    assert_error(
        client.put("/api/projects/99/campaign", json={"campaign_id": None}),
        404,
        "not_found",
    )
    left = client.put(url, json={"campaign_id": None})
    assert (left.status_code, left.json()["campaign_id"]) == (200, None)


def test_a_campaign_needs_a_known_caption_template(client: TestClient) -> None:
    message = assert_error(
        client.post(CAMPAIGNS, json={"name": "C", "caption_template": "gone"}),
        422,
        "validation_error",
    )
    created = add(client)
    patched = client.patch(
        f"{CAMPAIGNS}/{created['id']}", json={"caption_template": "boxed"}
    )

    assert "unknown template 'gone'" in message
    assert patched.json()["caption_template"] == "boxed"
    assert_error(
        client.patch(f"{CAMPAIGNS}/{created['id']}", json={"caption_template": "x"}),
        422,
        "validation_error",
    )


def test_campaign_check_lists_each_rule(client: TestClient, api_engine: Engine) -> None:
    campaign_id = ready_campaign(client)
    project_id, clip_id = project_with_clip(api_engine)
    client.put(
        f"/api/projects/{project_id}/campaign", json={"campaign_id": campaign_id}
    )

    passing = client.get(f"/api/clips/{clip_id}/campaign-check?platform=youtube")
    failing = client.get(f"/api/clips/{clip_id}/campaign-check?platform=tiktok")

    assert passing.status_code == 200
    body = passing.json()
    assert (body["passed"], body["campaign_id"], len(body["results"])) == (
        True,
        campaign_id,
        9,
    )
    assert failing.json()["passed"] is False
    assert_error(client.get("/api/clips/99/campaign-check"), 404, "not_found")
    assert_error(
        client.get(f"/api/clips/{clip_id}/campaign-check?platform=vimeo"),
        422,
        "validation_error",
    )


def test_publishing_is_409_with_the_failed_rules(
    client: TestClient, api_engine: Engine
) -> None:
    rules_publish_app(client)
    campaign_id = ready_campaign(client, required_hashtags=["creatorclips"])
    project_id, clip_id = project_with_clip(api_engine)
    client.put(
        f"/api/projects/{project_id}/campaign", json={"campaign_id": campaign_id}
    )
    client.patch(f"/api/clips/{clip_id}", json={"description": "No credit."})
    client.patch(f"{CAMPAIGNS}/{campaign_id}", json={"status": "paused"})
    publish = f"/api/test-publish-clip/{clip_id}"

    blocked = client.post(f"{publish}?platform=instagram")

    assert blocked.status_code == 409
    body = blocked.json()
    assert body["error"] == "campaign_rules_failed"
    assert [rule["rule"] for rule in body["failed"]] == [
        "campaign_status",
        "credit_line",
        "mentions",
        "platform",
    ]
    assert body["failed"][0] == {
        "rule": "campaign_status",
        "passed": False,
        "detail": "the campaign is paused",
    }
    assert body["message"].startswith(f"clip {clip_id} breaks campaign rules: ")

    client.patch(f"{CAMPAIGNS}/{campaign_id}", json={"status": "active"})
    client.put(
        f"/api/projects/{project_id}/campaign", json={"campaign_id": campaign_id}
    )
    assert client.post(f"{publish}?platform=youtube").json() == {"published": True}


def test_publishing_without_a_campaign_needs_source_rights(
    client: TestClient, api_engine: Engine
) -> None:
    rules_publish_app(client)
    _, unset = project_with_clip(api_engine, rights=None)
    _, ready = project_with_clip(api_engine)

    blocked = client.post(f"/api/test-publish-clip/{unset}")

    assert blocked.status_code == 409
    assert [rule["rule"] for rule in blocked.json()["failed"]] == ["source_rights"]
    assert client.post(f"/api/test-publish-clip/{ready}").status_code == 200
    assert_error(client.post("/api/test-publish-clip/99"), 404, "not_found")
