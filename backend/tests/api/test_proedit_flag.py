"""The Pro Edit feature flag on the API (SPEC-v3 0.13): GET /proedit/status
and GET /proedit/clips/{id}/variants answer while proedit.enabled is on,
and 404 proedit_disabled when it is off; the other endpoints do not
change."""

import pytest
from apihelpers import assert_error
from clipforge import config
from clipforge.proedit.config import ProEditConfig
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine


def turn_off_pro_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set proedit.enabled to false in config.settings."""
    off = config.settings.model_copy(update={"proedit": ProEditConfig(enabled=False)})
    monkeypatch.setattr(config, "settings", off)


def test_the_status_says_pro_edit_is_enabled(client: TestClient) -> None:
    response = client.get("/api/proedit/status")

    assert response.status_code == 200
    assert response.json() == {"enabled": True, "critic_max_rounds": 2}


def test_the_variants_of_a_clip_are_its_pro_edit_clips_oldest_first(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    original = add_clip(api_engine, project_id, "rendered", 80, "Pizza night")
    other = add_clip(api_engine, project_id, "rendered", 70, "Other")
    first = add_clip(
        api_engine,
        project_id,
        "candidate",
        0,
        "Pizza night — Pro Edit",
        parent_clip_id=original,
        variant="pro_edit",
    )
    add_clip(
        api_engine,
        project_id,
        "candidate",
        0,
        "Other — Pro Edit",
        parent_clip_id=other,
        variant="pro_edit",
    )
    second = add_clip(
        api_engine,
        project_id,
        "candidate",
        0,
        "Pizza night — Pro Edit",
        parent_clip_id=original,
        variant="pro_edit",
    )

    response = client.get(f"/api/proedit/clips/{original}/variants")

    assert response.status_code == 200
    variants = response.json()
    assert [v["id"] for v in variants] == [first, second]
    assert {(v["parent_clip_id"], v["variant"]) for v in variants} == {
        (original, "pro_edit")
    }
    assert client.get(f"/api/proedit/clips/{first}/variants").json() == []


def test_the_variants_of_a_missing_clip_are_not_found(client: TestClient) -> None:
    assert_error(client.get("/api/proedit/clips/99/variants"), 404, "not_found")


def test_pro_edit_endpoints_answer_proedit_disabled_when_it_is_off(
    client: TestClient, api_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "rendered", 80, "Pizza night")
    turn_off_pro_edit(monkeypatch)

    for path in ("/api/proedit/status", f"/api/proedit/clips/{clip_id}/variants"):
        message = assert_error(client.get(path), 404, "proedit_disabled")
        assert "proedit.enabled" in message
    clip = client.get(f"/api/clips/{clip_id}")
    assert (clip.status_code, clip.json()["title"]) == (200, "Pizza night")
