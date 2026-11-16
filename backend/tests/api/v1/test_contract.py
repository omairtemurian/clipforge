"""Contract tests of the public API /api/v1, generated from the app's
OpenAPI document: every operation it lists requires an API key (401
without one or with a wrong one, both documented), and with a valid key
each answers with a documented status and a body that matches the
documented schema. Queueing, publishing and approving or rejecting drafts
are human only (403)."""

from typing import Any

import pytest
from apihelpers import assert_error
from fastapi.testclient import TestClient
from openapi_check import Operation, load_document, public_operations, schema_errors

DOCUMENT = load_document()
OPERATIONS = public_operations(DOCUMENT)
HUMAN_ONLY = {
    "POST /api/v1/posts/{post_id}/queue",
    "POST /api/v1/posts/{post_id}/publish",
    "POST /api/v1/drafts/{draft_id}/approve",
    "POST /api/v1/drafts/{draft_id}/reject",
    "POST /api/v1/campaigns/{campaign_id}/drafts/approve",
}
# The automation loop that agents run (owner's request of 2026-10-31).
AUTOMATION_LOOP = {
    "POST /api/v1/projects",
    "POST /api/v1/projects/upload",
    "POST /api/v1/uploads",
    "GET /api/v1/jobs/{job_id}",
    "GET /api/v1/projects/{project_id}/clips",
    "GET /api/v1/clips/{clip_id}",
    "PATCH /api/v1/clips/{clip_id}",
    "GET /api/v1/clips/{clip_id}/transcript",
    "POST /api/v1/clips/{clip_id}/render",
    "GET /api/v1/clips/{clip_id}/download",
    "GET /api/v1/projects/{project_id}/download.zip",
    "GET /api/v1/brand-templates",
    "POST /api/v1/clips/{clip_id}/post-copy",
    "GET /api/v1/accounts",
    "POST /api/v1/clips/{clip_id}/posts",
    "POST /api/v1/posts/bulk-schedule",
    "GET /api/v1/posts",
    "GET /api/v1/posts/{post_id}",
}

each_operation = pytest.mark.parametrize(
    "operation", OPERATIONS, ids=[operation.label for operation in OPERATIONS]
)


def call(client: TestClient, operation: Operation, headers: dict[str, str]) -> Any:
    """Send operation with placeholder parameters and an empty JSON body."""
    return client.request(
        operation.method,
        operation.url(),
        json=operation.json_body(),
        headers=headers,
    )


def assert_documented(operation: Operation, response: Any) -> None:
    """Check that the answer's status is documented and its JSON body
    matches the documented schema."""
    schema = operation.response_schema(response.status_code)
    if schema is None or not response.headers.get("content-type", "").startswith(
        "application/json"
    ):
        return
    errors = schema_errors(response.json(), schema, DOCUMENT)
    assert errors == [], f"{operation.label}: {errors}"


def test_the_public_api_covers_the_automation_loop() -> None:
    labels = {operation.label for operation in OPERATIONS}

    assert AUTOMATION_LOOP <= labels
    assert HUMAN_ONLY <= labels
    assert not any("/api-keys" in label for label in labels)
    assert not any("/settings" in label for label in labels)


@each_operation
def test_every_operation_documents_the_key_and_its_errors(
    operation: Operation,
) -> None:
    assert operation.spec["security"] == [{"ApiKey": []}, {"Bearer": []}]
    for status in (401, 429, 404, 422):
        assert operation.response_schema(status) == {
            "$ref": "#/components/schemas/ErrorBody"
        }


def test_the_document_and_docs_are_served(client: TestClient) -> None:
    schemes = client.get("/api/openapi.json").json()["components"]["securitySchemes"]
    docs = client.get("/api/docs")

    assert schemes["ApiKey"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "An API key made in ClipForge (POST /api/api-keys).",
    }
    assert schemes["Bearer"]["scheme"] == "bearer"
    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()


@each_operation
def test_without_a_valid_key_every_operation_is_401(
    client: TestClient, operation: Operation
) -> None:
    missing = call(client, operation, {})
    wrong = [
        call(client, operation, {"X-API-Key": "cfk_wrong"}),
        call(client, operation, {"Authorization": "Bearer cfk_wrong"}),
    ]

    assert_error(missing, 401, "api_key_missing")
    assert missing.headers["www-authenticate"] == "Bearer"
    for response in [missing, *wrong]:
        assert_documented(operation, response)
    for response in wrong:
        assert_error(response, 401, "api_key_invalid")


@each_operation
def test_with_a_key_every_operation_answers_as_documented(
    client: TestClient, agent: dict[str, str], operation: Operation
) -> None:
    response = call(client, operation, agent)

    assert response.status_code not in (401, 429), response.text
    assert response.status_code < 500, response.text
    if operation.label in HUMAN_ONLY:
        assert_error(response, 403, "human_only")
    assert_documented(operation, response)
