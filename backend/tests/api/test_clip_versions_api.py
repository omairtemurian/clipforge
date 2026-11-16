"""Tests of the clip version endpoints (SPEC-v2 3.5, api/clip_versions):
edits through the API (PATCH /clips/{id}, the tracks endpoints) are listed
as versions; undo, redo and restore answer the clip with the version's
tracks and segments; errors are 404 and 409."""

from apihelpers import assert_error
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine

TEXT = {"id": "t", "kind": "text", "start": 0, "end": 1, "props": {"text": "Hi"}}


def edited_clip(client: TestClient, engine: Engine) -> tuple[int, dict, dict]:
    """Add a clip, move its end with PATCH and give it a text track; return
    its id, the clip before the edits and the clip after them."""
    clip_id = add_clip(engine, add_project(engine), "candidate", 80)
    before = client.get(f"/api/clips/{clip_id}").json()
    assert client.patch(f"/api/clips/{clip_id}", json={"end": 14.0}).status_code == 200
    after = client.patch(f"/api/clips/{clip_id}/tracks", json={"text": [TEXT]})
    assert after.status_code == 200
    return clip_id, before, after.json()


def test_api_edits_are_listed_as_versions(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id, before, after = edited_clip(client, api_engine)

    history = client.get(f"/api/clips/{clip_id}/versions").json()
    latest = client.get(f"/api/clips/{clip_id}/versions/3").json()

    assert (history["current"], history["can_undo"], history["can_redo"]) == (
        3,
        True,
        False,
    )
    assert [(v["number"], v["kind"], v["fields"]) for v in history["versions"]] == [
        (1, "original", []),
        (2, "edit", ["segments", "tracks"]),
        (3, "edit", ["tracks"]),
    ]
    assert latest["state"]["segments"] == after["segments"] == [[10.0, 14.0]]
    assert latest["state"]["tracks"] == after["tracks"]
    assert "state" not in history["versions"][0]
    assert before["segments"] == [[10.0, 12.5]]


def test_undo_redo_and_restore_answer_the_clip_at_that_version(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id, before, after = edited_clip(client, api_engine)

    client.post(f"/api/clips/{clip_id}/undo")
    undone = client.post(f"/api/clips/{clip_id}/undo")
    redone = client.post(f"/api/clips/{clip_id}/redo")
    restored = client.post(f"/api/clips/{clip_id}/versions/3/restore")

    assert undone.status_code == 200
    assert (undone.json()["segments"], undone.json()["tracks"]) == (
        before["segments"],
        before["tracks"],
    )
    assert redone.json()["segments"] == [[10.0, 14.0]]
    assert redone.json()["tracks"]["text"] == []
    assert restored.status_code == 200
    assert restored.json() == after
    assert client.get(f"/api/clips/{clip_id}").json() == after
    history = client.get(f"/api/clips/{clip_id}/versions").json()
    assert [(v["number"], v["kind"]) for v in history["versions"]] == [
        (1, "original"),
        (2, "edit"),
        (4, "restore"),
    ]
    assert history["versions"][-1]["restored_from"] == 3


def test_missing_clips_and_versions_are_404(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id, _, _ = edited_clip(client, api_engine)

    assert_error(client.get("/api/clips/999/versions"), 404, "not_found")
    assert_error(client.get(f"/api/clips/{clip_id}/versions/9"), 404, "not_found")
    assert_error(client.post("/api/clips/999/undo"), 404, "not_found")
    message = assert_error(
        client.post(f"/api/clips/{clip_id}/versions/9/restore"), 404, "not_found"
    )
    assert message == f"clip {clip_id} has no version 9"


def test_nothing_to_undo_or_redo_is_409(client: TestClient, api_engine: Engine) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)

    message = assert_error(client.post(f"/api/clips/{clip_id}/undo"), 409, "conflict")
    assert message == f"clip {clip_id} has nothing to undo"
    assert_error(client.post(f"/api/clips/{clip_id}/redo"), 409, "conflict")


def test_a_rendering_clip_is_not_moved(client: TestClient, api_engine: Engine) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "rendering", 80)

    for path in ("undo", "redo", "versions/1/restore"):
        assert_error(client.post(f"/api/clips/{clip_id}/{path}"), 409, "conflict")
