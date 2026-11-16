"""Tests of the speech enhancement setting through the API (SPEC-v2 3.5):
PUT /clips/{id}/enhance stores the strength as a version that undo takes
back; a clip has none until set; errors answer 404, 409 or 422."""

from apihelpers import assert_error
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine


def test_a_new_clip_has_no_enhancement(client: TestClient, api_engine: Engine) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)

    assert client.get(f"/api/clips/{clip_id}").json()["enhance"] == 0


def test_the_strength_is_saved_as_a_version_and_undo_takes_it_back(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)

    response = client.put(f"/api/clips/{clip_id}/enhance", json={"strength": 0.6})

    assert response.status_code == 200
    assert response.json()["enhance"] == 0.6
    assert client.get(f"/api/clips/{clip_id}").json()["enhance"] == 0.6
    history = client.get(f"/api/clips/{clip_id}/versions").json()
    assert history["versions"][-1]["fields"] == ["enhance"]
    assert client.post(f"/api/clips/{clip_id}/undo").json()["enhance"] == 0


def test_the_same_strength_again_adds_no_version(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    url = f"/api/clips/{clip_id}/enhance"
    client.put(url, json={"strength": 0.6})
    count = len(client.get(f"/api/clips/{clip_id}/versions").json()["versions"])

    client.put(url, json={"strength": 0.6})

    assert len(client.get(f"/api/clips/{clip_id}/versions").json()["versions"]) == count


def test_enhance_errors(client: TestClient, api_engine: Engine) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    rendering = add_clip(api_engine, project_id, "rendering", 80)

    assert_error(
        client.put("/api/clips/42/enhance", json={"strength": 0.5}), 404, "not_found"
    )
    assert_error(
        client.put(f"/api/clips/{rendering}/enhance", json={"strength": 0.5}),
        409,
        "conflict",
    )
    for body in ({"strength": 1.5}, {"strength": -0.1}, {}, {"strength": 0.5, "x": 1}):
        assert_error(
            client.put(f"/api/clips/{clip_id}/enhance", json=body),
            422,
            "validation_error",
        )
    assert client.get(f"/api/clips/{clip_id}").json()["enhance"] == 0
