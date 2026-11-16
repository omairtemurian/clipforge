"""MCP server of ClipForge (SPEC-v2 3.14): AI agents run the automation loop
through MCP tools that mirror the public REST API /api/v1 1:1 (clip
creation from a URL or a local file, job polling, clips and scores, text and
trim edits, render, post copy, draft schedules, post status).

It is a separate process that talks to the running ClipForge app over HTTP
with an API key, so every rule of the API applies: agents stop at drafts,
and queueing or publishing a post has no tool (and is 403 human_only if
asked for anyway). Run it from an MCP client:

    CLIPFORGE_API_KEY=cfk_... clipforge-mcp [--url URL] [--download-dir DIR]

It speaks MCP over stdio. A tool returns the API's JSON; a rendered video or
another file is saved in the download directory and its path returned.
"""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from email.message import Message
from pathlib import Path
from typing import Any

import anyio.to_thread
import httpx
import mcp_types as types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server

from clipforge.mcp_tools import Schema, ToolSpec, build_request, build_tools

DEFAULT_URL = "http://127.0.0.1:8000"
KEY_ENV = "CLIPFORGE_API_KEY"
URL_ENV = "CLIPFORGE_URL"
DEFAULT_DOWNLOADS = Path.home() / "clipforge-downloads"
OPENAPI_PATH = "/api/openapi.json"
TIMEOUT = 600.0
INSTRUCTIONS = (
    "Tools of ClipForge, a local video clipping app. Make a project from a "
    "URL (create_project) or a local file (upload_project), poll its job "
    "(list_project_jobs, get_job) until it is done, list the clips best "
    "first (list_clips with sort=score), edit them (patch_clip), render "
    "(queue_render, then poll the job), write post copy (post_copy) and make "
    "draft posts (create_posts, bulk_schedule). You cannot publish or queue "
    "posts: the owner approves drafts in the app."
)


class ClipForgeApi:
    """The running app's public API: sends the calls of the tools with an API
    key and turns each answer into MCP content."""

    def __init__(self, http: httpx.Client, download_dir: Path) -> None:
        self.http = http
        self.download_dir = download_dir

    def openapi(self) -> Schema:
        """Return the app's OpenAPI document (no key needed)."""
        response = self.http.get(OPENAPI_PATH)
        response.raise_for_status()
        document: Schema = response.json()
        return document

    def call(self, tool: ToolSpec, arguments: dict[str, Any]) -> types.CallToolResult:
        """Call tool with arguments and return its result: the API's JSON, or
        an error (is_error) for a wrong argument, an API error answer
        (status, error, message, retry_after_seconds on 429) or an app that
        does not answer."""
        try:
            request = build_request(tool, arguments)
            response = self.http.request(
                tool.method,
                request.url,
                params=request.params,
                json=request.json,
                data=request.data,
                files=request.files,
            )
        except ValueError as error:
            return _result(str(error), error=True)
        except httpx.HTTPError as error:
            return _result(f"Cannot reach ClipForge: {error}", error=True)
        if response.is_error:
            return _result(_error_text(response), error=True)
        return self._content(response)

    def _content(self, response: httpx.Response) -> types.CallToolResult:
        kind = response.headers.get("content-type", "").split(";")[0].strip()
        if response.status_code == 204 or not response.content:
            return _result(json.dumps({"ok": True}))
        if kind == "application/json":
            return _result(response.text)
        if kind.startswith("text/") or kind.endswith("+xml"):
            return _result(response.text)
        saved = self._save(response)
        return _result(
            json.dumps(
                {
                    "saved_to": str(saved),
                    "content_type": kind,
                    "bytes": saved.stat().st_size,
                }
            )
        )

    def _save(self, response: httpx.Response) -> Path:
        """Save a binary answer in the download directory and return its
        path, named as the answer says (else after its URL)."""
        header = Message()
        header["content-disposition"] = response.headers.get("content-disposition", "")
        name = header.get_filename() or response.url.path.rstrip("/").split("/")[-1]
        self.download_dir.mkdir(parents=True, exist_ok=True)
        target = self.download_dir / (Path(name).name or "download")
        target.write_bytes(response.content)
        return target


def _result(text: str, error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(text=text)], is_error=error)


def _error_text(response: httpx.Response) -> str:
    """Return the error answer as JSON: its status and its body (error,
    message), with the wait of a 429."""
    try:
        body = response.json()
    except ValueError:
        body = {"message": response.text}
    error: dict[str, Any] = {"status": response.status_code}
    error.update(body if isinstance(body, dict) else {"message": body})
    if "retry-after" in response.headers:
        error["retry_after_seconds"] = response.headers["retry-after"]
    return json.dumps(error)


def _annotations(tool: ToolSpec) -> types.ToolAnnotations:
    return types.ToolAnnotations(
        read_only_hint=tool.read_only,
        destructive_hint=tool.method == "DELETE",
        idempotent_hint=tool.method in {"GET", "PUT", "DELETE"},
        open_world_hint=False,
    )


def create_server(api: ClipForgeApi, tools: Sequence[ToolSpec]) -> Server[Any]:
    """Return the MCP server that offers tools and runs their calls on api."""
    by_name = {tool.name: tool for tool in tools}
    listed = [
        types.Tool(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            annotations=_annotations(tool),
        )
        for tool in tools
    ]

    async def list_tools(
        ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=listed)

    async def call_tool(
        ctx: ServerRequestContext[Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        tool = by_name.get(params.name)
        if tool is None:
            return _result(f"Unknown tool: {params.name}", error=True)
        return await anyio.to_thread.run_sync(
            api.call, tool, dict(params.arguments or {})
        )

    return Server(
        "clipforge",
        instructions=INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def connect(url: str, key: str, download_dir: Path) -> ClipForgeApi:
    """Return the API client of the app at url that sends key."""
    http = httpx.Client(base_url=url, headers={"X-API-Key": key}, timeout=TIMEOUT)
    return ClipForgeApi(http, download_dir)


async def serve(api: ClipForgeApi) -> None:
    """Serve the tools of the app's public API over stdio until the client
    disconnects."""
    tools = await anyio.to_thread.run_sync(lambda: build_tools(api.openapi()))
    server = create_server(api, tools)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of `clipforge-mcp`; return the exit status."""
    parser = argparse.ArgumentParser(
        prog="clipforge-mcp", description="ClipForge MCP server (stdio)."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get(URL_ENV, DEFAULT_URL),
        help=f"the running ClipForge app (default: ${URL_ENV} or {DEFAULT_URL})",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=DEFAULT_DOWNLOADS,
        help=f"where rendered videos and other files are saved (default: "
        f"{DEFAULT_DOWNLOADS})",
    )
    args = parser.parse_args(argv)
    key = os.environ.get(KEY_ENV, "")
    if not key:
        print(f"Set {KEY_ENV} to an API key (POST /api/api-keys).", file=sys.stderr)
        return 2
    try:
        asyncio.run(serve(connect(args.url, key, args.download_dir)))
    except httpx.HTTPError as error:
        print(f"Cannot read the API of {args.url}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
