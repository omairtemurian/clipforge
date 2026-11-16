"""Tests of the library search through the public API /api/v1 and MCP
(SPEC-v2 3.11, 3.14): an agent with an API key searches the transcripts and
makes a clip of a hit; the answers match the OpenAPI document and the MCP
tools mirror the operations."""

from pathlib import Path
from typing import Any

from apihelpers import assert_error
from clipforge.mcp_tools import build_tools
from fastapi.testclient import TestClient
from openapi_check import load_document, public_operations, schema_errors
from seed import add_project, add_work
from sqlalchemy import Engine

DOCUMENT = load_document()
OPERATIONS = {operation.label: operation for operation in public_operations(DOCUMENT)}
SEARCH_OPERATIONS = {
    "GET /api/v1/search": "search_library",
    "POST /api/v1/search/clips": "create_clip_from_moment",
}


def checked(response: Any, label: str, status: int) -> Any:
    """The body of response, after checking its status and its schema."""
    assert response.status_code == status, response.text
    body = response.json()
    schema = OPERATIONS[label].response_schema(status)
    assert schema is not None
    assert schema_errors(body, schema, DOCUMENT) == []
    return body


def test_every_search_operation_is_public_and_has_a_tool() -> None:
    tools = {f"{tool.method} {tool.path}": tool.name for tool in build_tools(DOCUMENT)}

    assert SEARCH_OPERATIONS.keys() <= OPERATIONS.keys()
    assert {op: tools[op] for op in SEARCH_OPERATIONS} == SEARCH_OPERATIONS


def test_an_agent_searches_and_clips_a_moment(
    client: TestClient, api_engine: Engine, agent: dict[str, str], sample_mp4: Path
) -> None:
    project = add_project(api_engine)
    add_work(api_engine, project, sample_mp4)

    hits = checked(
        client.get("/api/v1/search", params={"q": "hawk"}, headers=agent),
        "GET /api/v1/search",
        200,
    )
    assert [(h["project_id"], h["segment_id"]) for h in hits] == [(project, 5)]
    clip = checked(
        client.post(
            "/api/v1/search/clips",
            json={"project_id": project, "at": hits[0]["start"], "length": 10},
            headers=agent,
        ),
        "POST /api/v1/search/clips",
        201,
    )
    assert clip["start"] == 20.25


def test_search_needs_a_key(client: TestClient) -> None:
    assert_error(
        client.get("/api/v1/search", params={"q": "a"}), 401, "api_key_missing"
    )
