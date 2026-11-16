"""Tests of human-only approval (SPEC-v2 3.19): approving, rejecting and
approving all drafts of a campaign, like queueing, publishing and the
scheduling that queues, need the owner's local app session. A call with an
API key (the app's API or /api/v1) or through the MCP server gets 403
human_only and changes nothing; agents may still make drafts, list the
inbox and add review notes. The owner's session succeeds."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from api_key_fakes import make_key
from apihelpers import assert_error
from clipforge import posts
from clipforge.autopilot import inbox
from clipforge.mcp_server import ClipForgeApi, create_server
from clipforge.mcp_tools import ToolSpec, build_tools
from draft_fakes import SLOTS, Inbox, inbox_with_draft
from fastapi.testclient import TestClient
from mcp import Client
from post_api_fakes import AGENT
from sqlalchemy import Engine
from submission_fakes import campaign_clip

HUMAN_ONLY_TOOLS = {"approve_draft", "reject_draft", "approve_campaign_drafts"}
AGENT_TOOLS = {"list_drafts", "get_draft", "create_draft", "add_draft_note"}


@pytest.fixture
def setup(api_engine: Engine) -> Inbox:
    return inbox_with_draft(api_engine)


def human_only_calls(s: Inbox, post_id: int) -> list[tuple[str, str, Any]]:
    """(method, path under /api, JSON body) of every human-only action on
    the setup's draft, campaign, clip and draft post."""
    target = {"account_id": s.account_id}
    return [
        ("POST", f"/drafts/{s.draft_id}/approve", {}),
        ("POST", f"/drafts/{s.draft_id}/reject", {"reason": "boring"}),
        ("POST", f"/campaigns/{s.campaign_id}/drafts/approve", {}),
        ("POST", f"/posts/{post_id}/queue", {}),
        ("POST", f"/posts/{post_id}/publish", None),
        (
            "POST",
            "/posts/bulk-schedule",
            {
                "clip_ids": [s.clip_id],
                "targets": [target],
                "rules": SLOTS,
                "queue": True,
            },
        ),
    ]


APP_ONLY = [
    ("POST", "/campaigns/{campaign_id}/bulk-schedule"),
    ("POST", "/clips/{clip_id}/quick-post"),
    ("PUT", "/autopilot/pause"),
]


def draft_post(engine: Engine, s: Inbox) -> int:
    post = posts.create_post(
        engine, clip_id=s.clip_id, account_id=s.account_id, payload={"title": "Hi"}
    )
    return post.id


def assert_nothing_changed(engine: Engine, s: Inbox) -> None:
    assert inbox.get_draft(engine, s.draft_id).status == "pending"
    assert {p.status for p in posts.list_posts(engine)} <= {"draft"}


def test_an_api_key_gets_403_on_every_human_only_action(
    client: TestClient, api_engine: Engine, setup: Inbox
) -> None:
    key = {"X-API-Key": make_key(client)}
    post_id = draft_post(api_engine, setup)
    for method, path, body in human_only_calls(setup, post_id):
        for prefix, headers in (("/api", AGENT), ("/api", key), ("/api/v1", key)):
            response = client.request(method, prefix + path, json=body, headers=headers)
            assert_error(response, 403, "human_only")

    assert_nothing_changed(api_engine, setup)


@pytest.mark.parametrize(("method", "path"), APP_ONLY)
def test_app_only_queueing_actions_refuse_an_api_key(
    client: TestClient, setup: Inbox, method: str, path: str
) -> None:
    url = "/api" + path.format(campaign_id=setup.campaign_id, clip_id=setup.clip_id)
    body = {"clip_ids": [setup.clip_id], "rules": SLOTS, "queue": True}
    if "pause" in path:
        body = {"paused": False}
    response = client.request(method, url, json=body, headers=AGENT)

    assert_error(response, 403, "human_only")


def test_the_owners_session_approves_and_queues_the_posts(
    client: TestClient, api_engine: Engine, setup: Inbox
) -> None:
    response = client.post(f"/api/drafts/{setup.draft_id}/approve", json={})

    assert response.status_code == 200, response.text
    approval = response.json()
    assert approval["draft"]["status"] == "approved"
    assert [(p["account_id"], p["status"]) for p in approval["posts"]] == [
        (setup.account_id, "queued")
    ]
    assert approval["posts"][0]["scheduled_at"].startswith("2030-01-14T08:00")


def test_the_owners_session_rejects_and_approves_all(
    client: TestClient, api_engine: Engine, setup: Inbox
) -> None:
    rejected = client.post(f"/api/drafts/{setup.draft_id}/reject", json={})
    approved = client.post(
        f"/api/campaigns/{setup.campaign_id}/drafts/approve", json={}
    )

    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert approved.status_code == 200, approved.text
    assert approved.json() == []


def test_an_agent_makes_drafts_lists_the_inbox_and_adds_notes(
    client: TestClient, api_engine: Engine, setup: Inbox
) -> None:
    key = {"X-API-Key": make_key(client)}
    inbox.reject(api_engine, setup.draft_id, None)
    api = "/api/v1"

    listed = client.get(f"{api}/drafts", params={"status": "rejected"}, headers=key)
    clip_id = setup.clip_id
    exists = client.post(f"{api}/drafts", json={"clip_id": clip_id}, headers=key)
    one = client.get(f"{api}/drafts/{setup.draft_id}", headers=key)
    note = client.post(
        f"{api}/drafts/{setup.draft_id}/notes", json={"text": "Too long"}, headers=key
    )
    owner_note = client.post(
        f"/api/drafts/{setup.draft_id}/notes", json={"text": "Agreed"}
    )

    assert listed.status_code == 200, listed.text
    assert [d["id"] for d in listed.json()] == [setup.draft_id]
    assert_error(exists, 409, "draft_exists")
    assert one.status_code == 200
    assert note.status_code == 201, note.text
    assert owner_note.status_code == 201, owner_note.text
    notes = [(n["text"], n["by"]) for n in owner_note.json()["notes"]]
    assert notes == [("Too long", "agent"), ("Agreed", "owner")]


def test_through_mcp_an_agent_drafts_and_cannot_approve(
    client: TestClient, api_engine: Engine, setup: Inbox, tmp_path: Path
) -> None:
    http = TestClient(client.app, headers={"X-API-Key": make_key(client)})
    api = ClipForgeApi(http, tmp_path)
    tools = build_tools(api.openapi())
    names = {tool.name for tool in tools}
    inbox.reject(api_engine, setup.draft_id, None)
    clip_id = campaign_clip(api_engine, setup.campaign_id, "Second")

    async def scenario() -> tuple[Any, Any, str]:
        async with Client(create_server(api, tools)) as mcp:
            made = await mcp.call_tool("create_draft", {"clip_id": clip_id})
            draft_id = json.loads(_text(made))["id"]
            noted = await mcp.call_tool(
                "add_draft_note", {"draft_id": draft_id, "text": "Bad crop"}
            )
            approve = await mcp.call_tool("approve_draft", {"draft_id": draft_id})
            return json.loads(_text(made)), json.loads(_text(noted)), _text(approve)

    made, noted, approve = asyncio.run(scenario())

    assert AGENT_TOOLS <= names
    assert HUMAN_ONLY_TOOLS.isdisjoint(names)
    assert made["status"] == "pending"
    assert noted["notes"][0]["by"] == "agent"
    assert "Unknown tool" in approve
    assert inbox.get_draft(api_engine, made["id"]).status == "pending"


def test_the_server_refuses_an_approve_tool_call_that_gets_through(
    client: TestClient, setup: Inbox, tmp_path: Path
) -> None:
    http = TestClient(client.app, headers={"X-API-Key": make_key(client)})
    tool = ToolSpec(
        name="approve_draft",
        description="",
        method="POST",
        path="/api/v1/drafts/{draft_id}/approve",
        input_schema={"properties": {"draft_id": {}}, "required": ["draft_id"]},
        path_params=("draft_id",),
        query_params=(),
        body_kind="json",
        body_fields=(),
        file_fields=(),
    )

    result = ClipForgeApi(http, tmp_path).call(tool, {"draft_id": setup.draft_id})

    assert result.is_error
    assert json.loads(_text(result))["error"] == "human_only"


def _text(result: Any) -> str:
    (block,) = result.content
    return str(block.text)
