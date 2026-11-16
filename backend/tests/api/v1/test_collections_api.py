"""Tests of the collections through the public API /api/v1 and MCP (SPEC-v2
3.11, 3.14): an agent with an API key makes a collection, adds clips, reads
it and downloads its zip; every answer matches the OpenAPI document and the
MCP tools mirror the operations."""

import io
import zipfile
from typing import Any

from apihelpers import assert_error
from clipforge.mcp_tools import build_tools
from clipforge.pipeline.render import clip_output
from fastapi.testclient import TestClient
from openapi_check import load_document, public_operations, schema_errors
from seed import add_clip, add_project
from sqlalchemy import Engine

DOCUMENT = load_document()
OPERATIONS = {operation.label: operation for operation in public_operations(DOCUMENT)}
ITEM = "DELETE /api/v1/collections/{collection_id}/items/{clip_id}"
ZIP = "GET /api/v1/collections/{collection_id}/download.zip"
COLLECTION_OPERATIONS = {
    "GET /api/v1/collections": "list_collections",
    "POST /api/v1/collections": "create_collection",
    "GET /api/v1/collections/{collection_id}": "get_collection",
    "PATCH /api/v1/collections/{collection_id}": "update_collection",
    "DELETE /api/v1/collections/{collection_id}": "delete_collection",
    "POST /api/v1/collections/{collection_id}/items": "add_collection_clips",
    ITEM: "remove_collection_clip",
    ZIP: "download_collection_zip",
}


def send(
    client: TestClient,
    agent: dict[str, str],
    method: str,
    path: str,
    url: str,
    status: int,
    **kw: Any,
) -> Any:
    """Send url (of operation path) with the key; check the status and that
    the body matches the documented schema."""
    response = client.request(method, url, headers=agent, **kw)
    assert response.status_code == status, response.text
    schema = OPERATIONS[f"{method} /api/v1{path}"].response_schema(status)
    if schema is None or not response.headers["content-type"].startswith(
        "application/json"
    ):
        return response
    body = response.json()
    assert schema_errors(body, schema, DOCUMENT) == []
    return body


def test_every_collection_operation_is_public_and_has_a_tool() -> None:
    tools = {f"{tool.method} {tool.path}": tool.name for tool in build_tools(DOCUMENT)}

    assert COLLECTION_OPERATIONS.keys() <= OPERATIONS.keys()
    assert {op: tools[op] for op in COLLECTION_OPERATIONS} == COLLECTION_OPERATIONS


def test_an_agent_collects_clips_and_downloads_the_zip(
    client: TestClient, api_engine: Engine, agent: dict[str, str]
) -> None:
    project = add_project(api_engine)
    clip_id = add_clip(api_engine, project, "rendered", 88, "Hit")
    video = clip_output(project, clip_id)
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"video")
    base = "/api/v1/collections"

    made = send(
        client, agent, "POST", "/collections", base, 201, json={"name": "Weekly"}
    )
    item_path = "/collections/{collection_id}/items"
    one = f"{base}/{made['id']}"
    added = send(
        client,
        agent,
        "POST",
        item_path,
        f"{one}/items",
        200,
        json={"clip_ids": [clip_id]},
    )
    assert [item["clip_id"] for item in added["items"]] == [clip_id]
    send(client, agent, "GET", "/collections", base, 200)
    send(client, agent, "GET", "/collections/{collection_id}", one, 200)
    send(
        client, agent, "PATCH", "/collections/{collection_id}", one, 200,
        json={"description": "Week 44"},
    )  # fmt: skip
    archive = send(
        client, agent, "GET", "/collections/{collection_id}/download.zip",
        f"{one}/download.zip", 200,
    )  # fmt: skip
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
        assert set(zipped.namelist()) == {f"{clip_id}.mp4", "manifest.json"}
    removed = send(
        client, agent, "DELETE", "/collections/{collection_id}/items/{clip_id}",
        f"{one}/items/{clip_id}", 200,
    )  # fmt: skip
    assert removed["items"] == []
    send(client, agent, "DELETE", "/collections/{collection_id}", one, 204)
    missing = client.get(one, headers=agent)
    assert_error(missing, 404, "not_found")


def test_collections_need_a_key(client: TestClient) -> None:
    assert_error(client.get("/api/v1/collections"), 401, "api_key_missing")
