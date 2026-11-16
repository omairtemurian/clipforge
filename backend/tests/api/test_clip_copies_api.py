"""Tests of the duplicate and split endpoints (SPEC-v2 3.5, api/clip_copies):
a copy and a second part are new candidate clips; errors are 404, 409 and
422; both clips of a split have a version history."""

from apihelpers import assert_error
from clipforge.models import ClipStatus
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine

# The seeded clip plays 10-12.5 s of a 60 s source.


def new_clip(engine: Engine, status: ClipStatus = "rendered") -> int:
    """Add a clip (seed.add_clip) with status; return its id."""
    return add_clip(engine, add_project(engine), status, 80, title="Pizza")


def test_duplicate_adds_a_candidate_copy(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = new_clip(api_engine)

    response = client.post(f"/api/clips/{clip_id}/duplicate")

    assert response.status_code == 201
    copy = response.json()
    assert copy["id"] != clip_id
    assert (copy["status"], copy["output_path"]) == ("candidate", None)
    assert copy["segments"] == [[10.0, 12.5]]
    listed = client.get(f"/api/clips/{copy['id']}")
    assert listed.json()["title"] == "Pizza (copy)"
    assert client.get(f"/api/clips/{clip_id}").json()["status"] == "rendered"


def test_split_answers_both_clips(client: TestClient, api_engine: Engine) -> None:
    clip_id = new_clip(api_engine)

    response = client.post(f"/api/clips/{clip_id}/split", json={"at": 11.0})

    assert response.status_code == 201
    first, second = response.json()
    assert first["id"] == clip_id and second["id"] != clip_id
    assert first["segments"] == [[10.0, 11.0]]
    assert second["segments"] == [[11.0, 12.5]]
    assert second["status"] == "candidate"
    original = client.get(f"/api/clips/{clip_id}/versions").json()["versions"]
    assert [v["kind"] for v in original][0] == "original"


def test_split_errors(client: TestClient, api_engine: Engine) -> None:
    clip_id = new_clip(api_engine)
    rendering = new_clip(api_engine, "rendering")

    assert_error(
        client.post("/api/clips/999/split", json={"at": 11.0}), 404, "not_found"
    )
    assert_error(client.post("/api/clips/999/duplicate"), 404, "not_found")
    assert_error(
        client.post(f"/api/clips/{clip_id}/split", json={"at": 30.0}),
        422,
        "validation_error",
    )
    assert_error(
        client.post(f"/api/clips/{clip_id}/split", json={"at": 0}),
        422,
        "validation_error",
    )
    assert_error(
        client.post(f"/api/clips/{rendering}/split", json={"at": 11.0}), 409, "conflict"
    )
