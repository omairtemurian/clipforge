"""Tests of the MCP server (SPEC-v2 3.14) through the MCP protocol: an agent
runs the automation loop with tools that call /api/v1 with an API key (the
app is real, the LLM a fake), and cannot queue or publish."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import mcp_types as types
import pytest
from api_key_fakes import make_key
from clipforge import mcp_server
from clipforge.api.app import create_app
from clipforge.mcp_server import ClipForgeApi, create_server
from clipforge.mcp_tools import ToolSpec, build_tools
from fakes import FIXTURES, FakeLLMClient
from fastapi.testclient import TestClient
from loop_fakes import finish_render, processed_clip
from mcp import Client
from openapi_check import load_document
from post_api_fakes import LATER, accounts
from sqlalchemy import Engine

REPLY = json.loads((FIXTURES / "post_copy" / "replies.json").read_text())["first"]
URL = "https://www.youtube.com/watch?v=abc"


@asynccontextmanager
async def agent_session(http: httpx.Client, downloads: Path) -> AsyncIterator[Client]:
    """An MCP client connected in process to the server of the app at http."""
    api = ClipForgeApi(http, downloads)
    server = create_server(api, build_tools(api.openapi()))
    async with Client(server) as client:
        yield client


async def call(client: Client, name: str, **arguments: Any) -> Any:
    """Call a tool, check that it succeeded and return its JSON."""
    result = await client.call_tool(name, arguments)
    assert not result.is_error, result.content
    return json.loads(_text(result))


def _text(result: types.CallToolResult) -> str:
    (block,) = result.content
    assert isinstance(block, types.TextContent)
    return block.text


def run(
    app_client: TestClient,
    key: str,
    downloads: Path,
    scenario: Callable[[Client], Awaitable[Any]],
) -> Any:
    """Run scenario with an MCP client whose server uses key."""
    http = TestClient(app_client.app, headers={"X-API-Key": key})

    async def main() -> Any:
        async with agent_session(http, downloads) as client:
            return await scenario(client)

    return asyncio.run(main())


def test_an_agent_runs_the_loop_through_mcp(
    data_dir: Path, sample_mp4: Path, tmp_path: Path
) -> None:
    llm = FakeLLMClient(json.dumps(REPLY))
    app = create_app(run_worker=False, caption_previews=False, llm=llm)
    with TestClient(app) as owner:
        engine: Engine = owner.app.state.engine  # type: ignore[attr-defined]
        key = make_key(owner)
        project_id, clip_id = processed_clip(engine, sample_mp4)
        (account_id,) = accounts(engine, "tiktok")

        async def scenario(client: Client) -> dict[str, Any]:
            seen: dict[str, Any] = {}
            project = await call(client, "create_project", url=URL)
            (job,) = await call(client, "list_project_jobs", project_id=project["id"])
            polled = await call(client, "get_job", job_id=job["id"])
            seen["job"] = (polled["kind"], polled["status"])
            clips = await call(
                client, "list_clips", project_id=project_id, sort="score"
            )
            seen["clips"] = [(c["id"], c["scores"]["overall"]) for c in clips]
            edited = await call(
                client, "patch_clip", clip_id=clip_id, title="Best pizza", start=10.5
            )
            seen["edit"] = (edited["title"], edited["start"])
            render = await call(client, "queue_render", clip_id=clip_id)
            seen["render"] = (render["kind"], render["status"])
            finish_render(engine, project_id, clip_id)
            seen["download"] = await call(client, "download_clip", clip_id=clip_id)
            copy = await call(client, "post_copy", clip_id=clip_id, platform="tiktok")
            seen["accounts"] = [a["id"] for a in await call(client, "list_accounts")]
            target = {"account_id": account_id, "text": {"caption": copy["caption"]}}
            (draft,) = await call(
                client,
                "create_posts",
                clip_id=clip_id,
                targets=[target],
                scheduled_at=LATER,
            )
            seen["draft"] = (draft["status"], draft["scheduled_at"])
            posts = await call(client, "list_posts", clip_id=clip_id)
            seen["posts"] = [(p["id"], p["status"]) for p in posts]
            seen["draft_id"] = draft["id"]
            return seen

        seen = run(owner, key, tmp_path / "downloads", scenario)
    assert seen["job"] == ("process", "queued")
    assert seen["clips"] == [(clip_id, 82)]
    assert seen["edit"] == ("Best pizza", 10.5)
    assert seen["render"] == ("render", "queued")
    assert seen["accounts"] == [account_id]
    assert seen["draft"] == ("draft", LATER)
    assert seen["posts"] == [(seen["draft_id"], "draft")]
    saved = Path(seen["download"]["saved_to"])
    assert saved.parent == tmp_path / "downloads"
    assert saved.stat().st_size == seen["download"]["bytes"] > 0
    assert seen["download"]["content_type"] == "video/mp4"


def test_the_agent_has_no_tool_to_queue_or_publish(
    client: TestClient, tmp_path: Path
) -> None:
    key = make_key(client)

    async def scenario(mcp: Client) -> tuple[set[str], str, str]:
        listed = {tool.name for tool in (await mcp.list_tools()).tools}
        unknown = await mcp.call_tool("publish_now", {"post_id": 1})
        queued = await mcp.call_tool(
            "bulk_schedule",
            {"clip_ids": [1], "targets": [], "rules": {}, "queue": True},
        )
        return listed, _text(unknown), _text(queued)

    listed, unknown, queued = run(client, key, tmp_path, scenario)
    assert {"queue_post", "publish_now"}.isdisjoint(listed)
    assert "Unknown tool" in unknown
    assert "unknown argument" in queued


def test_the_server_answers_403_when_a_call_gets_through_anyway(
    client: TestClient, tmp_path: Path
) -> None:
    http = TestClient(client.app, headers={"X-API-Key": make_key(client)})
    tool = ToolSpec(
        name="publish_now",
        description="",
        method="POST",
        path="/api/v1/posts/{post_id}/publish",
        input_schema={"properties": {"post_id": {}}, "required": ["post_id"]},
        path_params=("post_id",),
        query_params=(),
        body_kind=None,
        body_fields=(),
        file_fields=(),
    )
    result = ClipForgeApi(http, tmp_path).call(tool, {"post_id": 1})
    assert result.is_error
    assert json.loads(_text(result))["error"] == "human_only"


def test_an_api_error_comes_back_as_a_tool_error(
    client: TestClient, tmp_path: Path
) -> None:
    key = make_key(client)

    async def scenario(mcp: Client) -> types.CallToolResult:
        return await mcp.call_tool("get_job", {"job_id": 987654})

    result = run(client, key, tmp_path, scenario)
    assert result.is_error
    body = json.loads(_text(result))
    assert body["status"] == 404
    assert body["error"]


def test_a_wrong_key_is_a_tool_error(client: TestClient, tmp_path: Path) -> None:
    async def scenario(mcp: Client) -> types.CallToolResult:
        return await mcp.call_tool("list_posts", {})

    result = run(client, "cfk_wrong", tmp_path, scenario)
    assert result.is_error
    assert json.loads(_text(result))["error"] == "api_key_invalid"


def test_a_local_file_becomes_a_project(
    client: TestClient, sample_mp4: Path, tmp_path: Path
) -> None:
    key = make_key(client)

    async def scenario(mcp: Client) -> dict[str, Any]:
        return await call(  # type: ignore[no-any-return]
            mcp,
            "upload_project",
            file=str(sample_mp4),
            source_rights="own",
            settings={"num_clips": 3},
        )

    project = run(client, key, tmp_path, scenario)
    assert project["source_rights"] == "own"
    assert project["source_path"].endswith("sample.mp4")
    assert project["settings"]["num_clips"] == 3


def test_a_rate_limit_answer_tells_how_long_to_wait(tmp_path: Path) -> None:
    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"Retry-After": "17"},
            json={"error": "rate_limited", "message": "Slow down."},
        )

    http = httpx.Client(base_url="http://app", transport=httpx.MockTransport(limited))
    api = ClipForgeApi(http, tmp_path)
    (tool,) = [t for t in build_tools(load_document()) if t.name == "list_posts"]
    result = api.call(tool, {})
    assert result.is_error
    assert json.loads(_text(result)) == {
        "status": 429,
        "error": "rate_limited",
        "message": "Slow down.",
        "retry_after_seconds": "17",
    }


def test_an_app_that_is_down_is_a_tool_error(tmp_path: Path) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    http = httpx.Client(base_url="http://app", transport=httpx.MockTransport(down))
    api = ClipForgeApi(http, tmp_path)
    (tool,) = [t for t in build_tools(load_document()) if t.name == "list_posts"]
    result = api.call(tool, {})
    assert result.is_error
    assert "Cannot reach ClipForge" in _text(result)


def test_the_server_needs_an_api_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(mcp_server.KEY_ENV, raising=False)
    assert mcp_server.main([]) == 2
    assert mcp_server.KEY_ENV in capsys.readouterr().err
