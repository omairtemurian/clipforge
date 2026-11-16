"""Helpers of the post API tests (tests only): a rendered clip with source
rights, connected accounts and draft posts made through the API."""

from pathlib import Path
from typing import Any

from clipforge.models import SocialPlatform
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from social_fakes import add_account, clip_of, set_rights, write_video
from sqlalchemy import Engine

# An agent's call (API key); the MCP server calls the API with one too.
AGENT = {"X-API-Key": "cf_agent_key"}
LATER = "2030-01-15T09:00:00Z"


def rendered_clip(engine: Engine, title: str = "Pizza night") -> int:
    """Add a rendered clip (its video exists) of a project with source
    rights and return its id."""
    project_id = add_project(engine)
    set_rights(engine, project_id, "own")
    clip_id = add_clip(engine, project_id, "rendered", 70, title)
    output = clip_of(engine, clip_id).output_path
    assert output is not None
    write_video(Path(output))
    return clip_id


def accounts(engine: Engine, *platforms: SocialPlatform) -> list[int]:
    """Connect an account of each platform and return their ids."""
    return [
        add_account(engine, f"{platform}-{index}", platform)
        for index, platform in enumerate(platforms)
    ]


def make_drafts(
    client: TestClient,
    clip_id: int,
    targets: list[dict[str, Any]],
    **body: Any,
) -> list[dict[str, Any]]:
    """Make draft posts through the API and return them."""
    response = client.post(
        f"/api/clips/{clip_id}/posts", json={"targets": targets} | body
    )
    assert response.status_code == 201, response.text
    drafts: list[dict[str, Any]] = response.json()
    return drafts


def make_draft(client: TestClient, clip_id: int, account_id: int, **text: Any) -> int:
    """Make one draft post of clip_id to account_id saying text; its id."""
    target = {"account_id": account_id, "text": text}
    return int(make_drafts(client, clip_id, [target])[0]["id"])
