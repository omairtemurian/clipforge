"""Tests of manual subject tracking (SPEC-v2 3.3, TASK-82): a click or a box
at a time t of the clip, followed through the scene by
POST /clips/{id}/scenes/track on a synthetic moving square, and the list of
the genre reframing presets (GET /reframe-presets)."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from moving_square import make_moving_square, square_x
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine

PRESETS = ["podcast-2", "standup", "gaming", "vlog"]


@pytest.fixture(scope="module")
def square(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The 4 s moving square video (tests/moving_square)."""
    return make_moving_square(tmp_path_factory.mktemp("manual") / "square.mp4")


def seed_clip(api_engine: Engine, video: Path, start: float, end: float) -> int:
    """Add a clip from start to end of the square video; return its id."""
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80, start=start, end=end)
    add_work(api_engine, project_id, video)
    return clip_id


def track(
    client: TestClient, clip_id: int, start: float, end: float, seed: dict[str, Any]
) -> dict[str, Any]:
    """POST the scene to track and return the JSON of the reply."""
    response = client.post(
        f"/api/clips/{clip_id}/scenes/track",
        json={"start": start, "end": end, "seed": seed},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def assert_follows(body: dict[str, Any], first: float, last: float) -> None:
    """Check the keyframes of body follow the square from first to last s."""
    inner = [p for p in body["keyframes"] if first <= p["t"] <= last]
    assert len(inner) >= 5
    assert all(abs(p["x"] - square_x(p["t"])) < 0.06 for p in inner)
    xs = [p["x"] for p in body["keyframes"]]
    assert xs == sorted(xs)


@pytest.mark.slow
def test_a_click_at_a_time_in_the_clip_is_followed_forward_and_back(
    client: TestClient, api_engine: Engine, square: Path
) -> None:
    clip_id = seed_clip(api_engine, square, 0.0, 4.0)
    click = {"t": 2.0, "x": round(square_x(2.0), 4), "y": 0.5, "width": 0, "height": 0}

    body = track(client, clip_id, 0.0, 4.0, click)

    assert body["seed"]["t"] == 2.0 and body["seed"]["width"] > 0
    assert body["keyframes"][0]["t"] == 0.0
    assert_follows(body, 0.5, 3.5)


@pytest.mark.slow
def test_a_box_at_a_time_in_the_clip_is_followed_from_there(
    client: TestClient, api_engine: Engine, square: Path
) -> None:
    clip_id = seed_clip(api_engine, square, 0.0, 4.0)
    box = {"t": 1.0, "x": 0.25, "y": 0.4167, "width": 0.0938, "height": 0.1667}

    body = track(client, clip_id, 0.0, 4.0, box)

    assert body["seed"] == box
    assert_follows(body, 0.5, 3.5)


def test_the_presets_are_listed_with_their_parameters(client: TestClient) -> None:
    response = client.get("/api/reframe-presets")

    assert response.status_code == 200
    body = response.json()
    assert [row["name"] for row in body] == PRESETS
    gaming = next(row for row in body if row["name"] == "gaming")
    assert gaming["layout"] == "fit" and gaming["objects"] is False
    podcast = body[0]
    assert podcast["layout"] is None and podcast["split_share"] == 0.4
    assert all(row["label"] and row["description"] for row in body)
