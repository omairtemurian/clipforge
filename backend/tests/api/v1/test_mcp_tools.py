"""Tests of the MCP tools (SPEC-v2 3.14): one per operation of the public API
/api/v1 with a valid JSON Schema of its inputs, none for queueing or
publishing, and the requests that tool calls make."""

from pathlib import Path
from typing import Any

import pytest
from clipforge.mcp_tools import ToolSpec, build_request, build_tools
from jsonschema import Draft202012Validator
from openapi_check import load_document, public_operations

DOCUMENT = load_document()
TOOLS = {tool.name: tool for tool in build_tools(DOCUMENT)}
EXCLUDED = {
    "POST /api/v1/posts/{post_id}/queue",
    "POST /api/v1/posts/{post_id}/publish",
    "POST /api/v1/drafts/{draft_id}/approve",
    "POST /api/v1/drafts/{draft_id}/reject",
    "POST /api/v1/campaigns/{campaign_id}/drafts/approve",
    "POST /api/v1/uploads",
    "GET /api/v1/uploads/{upload_id}",
    "PATCH /api/v1/uploads/{upload_id}",
    "DELETE /api/v1/uploads/{upload_id}",
    "POST /api/v1/uploads/{upload_id}/complete",
    "GET /api/v1/jobs/{job_id}/events",
    "POST /api/v1/clips/{clip_id}/thumbnail/upload",
}
LOOP_TOOLS = {
    "create_project",
    "upload_project",
    "list_project_jobs",
    "get_job",
    "list_clips",
    "get_clip",
    "patch_clip",
    "get_clip_transcript",
    "queue_render",
    "download_clip",
    "post_copy",
    "list_accounts",
    "create_posts",
    "bulk_schedule",
    "list_posts",
    "get_post",
}


def test_tools_mirror_the_api_except_what_agents_may_not_do() -> None:
    operations = {op.label for op in public_operations(DOCUMENT)}
    called = {f"{tool.method} {tool.path}" for tool in TOOLS.values()}
    assert called == operations - EXCLUDED
    assert len(TOOLS) == len(called)


def test_the_automation_loop_has_tools() -> None:
    assert LOOP_TOOLS <= set(TOOLS)


def test_approve_and_publish_are_not_exposed() -> None:
    forbidden = {
        "queue_post",
        "publish_now",
        "approve_post",
        "approve_draft",
        "reject_draft",
        "approve_campaign_drafts",
    }
    assert forbidden.isdisjoint(TOOLS)
    assert all(
        "/queue" not in t.path and "/publish" not in t.path for t in TOOLS.values()
    )
    assert "queue" not in TOOLS["bulk_schedule"].input_schema["properties"]


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_every_input_schema_is_valid_json_schema(name: str) -> None:
    schema = TOOLS[name].input_schema
    Draft202012Validator.check_schema(schema)
    assert schema["type"] == "object"
    assert TOOLS[name].description
    unresolved = [r for r in _refs(schema) if not r.startswith("#/$defs/")]
    assert unresolved == []
    assert all(r.removeprefix("#/$defs/") in schema["$defs"] for r in _refs(schema))


def _refs(node: Any) -> list[str]:
    if isinstance(node, list):
        return [r for item in node for r in _refs(item)]
    if not isinstance(node, dict):
        return []
    found = [node["$ref"]] if isinstance(node.get("$ref"), str) else []
    return found + [r for value in node.values() for r in _refs(value)]


def test_body_fields_are_inputs_of_the_tool() -> None:
    schema = TOOLS["create_posts"].input_schema
    assert set(schema["properties"]) == {
        "clip_id",
        "targets",
        "scheduled_at",
        "thumbnail_asset_id",
    }
    assert set(schema["required"]) == {"clip_id", "targets"}
    validator = Draft202012Validator(schema)
    good = {"clip_id": 1, "targets": [{"account_id": 2, "text": {"caption": "c"}}]}
    assert list(validator.iter_errors(good)) == []
    assert list(validator.iter_errors({"clip_id": "x", "targets": []})) != []


def test_a_call_becomes_a_request() -> None:
    request = build_request(
        TOOLS["patch_clip"], {"clip_id": 7, "title": "Best pizza", "start": 12.5}
    )
    assert request.url == "/api/v1/clips/7"
    assert request.json == {"title": "Best pizza", "start": 12.5}
    listing = build_request(TOOLS["list_clips"], {"project_id": 3, "sort": "score"})
    assert (listing.url, listing.params, listing.json) == (
        "/api/v1/projects/3/clips",
        {"sort": "score"},
        None,
    )


def test_a_local_file_is_uploaded_as_a_form() -> None:
    tool: ToolSpec = TOOLS["upload_project"]
    assert tool.file_fields == ("file",)
    assert tool.input_schema["properties"]["file"]["type"] == "string"


def test_wrong_arguments_are_named(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown argument.*queue"):
        build_request(TOOLS["bulk_schedule"], {"queue": True})
    with pytest.raises(ValueError, match="missing argument.*clip_id"):
        build_request(TOOLS["get_clip"], {})
    with pytest.raises(ValueError, match="is not a file"):
        build_request(TOOLS["upload_project"], {"file": str(tmp_path / "no.mp4")})


def test_a_body_that_is_not_an_object_is_the_input_body() -> None:
    document = {
        "paths": {
            "/api/v1/things": {
                "put": {
                    "operationId": "put_things_api_v1_things_put",
                    "summary": "Put things",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"type": "string"}}
                            }
                        },
                    },
                }
            }
        }
    }
    (tool,) = build_tools(document)
    assert tool.input_schema["required"] == ["body"]
    request = build_request(tool, {"body": ["a", "b"]})
    assert request.json == ["a", "b"]
