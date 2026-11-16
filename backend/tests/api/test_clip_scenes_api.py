"""Tests of a clip's scenes: GET /clips/{id}/scenes and saving them with
PATCH /clips/{id} (STEERING item 7)."""

from pathlib import Path
from typing import Any

from apihelpers import assert_error
from builders import cut
from clipforge.db import ClipRow
from clipforge.models import SignalList
from clipforge.pipeline.step import SIGNALS, write_json
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


def scene(start: float, end: float, **fields: Any) -> dict[str, Any]:
    """The JSON of a scene from start to end seconds, with fields."""
    return {"start": start, "end": end, **fields}


def test_scenes_split_the_clip_at_the_scene_cuts_inside_it(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    work = add_work(api_engine, project_id, sample_mp4)
    write_json(work / SIGNALS, SignalList([cut(5.0), cut(10.3), cut(11.0), cut(12.2)]))

    response = client.get(f"/api/clips/{clip_id}/scenes")

    assert response.status_code == 200
    body = response.json()
    assert body["cuts"] == [5.0, 10.3, 11.0, 12.2]
    assert [(s["start"], s["end"], s["mode"], s["layout"]) for s in body["scenes"]] == [
        (10.0, 11.0, "auto", "fill"),
        (11.0, 12.5, "auto", "fill"),
    ]


def test_stored_scenes_are_returned_and_follow_a_trim(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    work = add_work(api_engine, project_id, sample_mp4)
    write_json(work / SIGNALS, SignalList([cut(11.0)]))
    fixed = scene(
        11.0005,
        12.5,
        mode="fixed",
        crop_keyframes=[{"t": 11.5, "x": 0.25, "y": 0.5}],
        scale=0.5,
    )
    scenes = [scene(10.0, 11.0, layout="fit"), fixed]

    saved = client.patch(f"/api/clips/{clip_id}", json={"scene_reframes": scenes})
    trimmed = client.patch(f"/api/clips/{clip_id}", json={"start": 10.5, "end": 12})
    response = client.get(f"/api/clips/{clip_id}/scenes")

    assert saved.status_code == 200
    assert [s["start"] for s in saved.json()["scene_reframes"]] == [10.0, 11.0]
    assert trimmed.status_code == 200
    stored = response.json()["scenes"]
    assert [(s["start"], s["end"], s["layout"], s["mode"]) for s in stored] == [
        (10.5, 11.0, "fit", "auto"),
        (11.0, 12.0, "fill", "fixed"),
    ]
    assert stored[1]["crop_keyframes"] == [{"t": 11.5, "x": 0.25, "y": 0.5}]
    assert stored[1]["scale"] == 0.5
    with Session(api_engine) as session:
        clip = session.get_one(ClipRow, clip_id).to_model()
    assert [s.end for s in clip.scene_reframes] == [11.0, 12.0]
    cleared = client.patch(f"/api/clips/{clip_id}", json={"scene_reframes": []})
    assert cleared.json()["scene_reframes"] == []


def test_scenes_need_a_clip_and_its_signals(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)

    assert_error(client.get("/api/clips/999/scenes"), 404, "not_found")
    add_work(api_engine, project_id, sample_mp4)
    assert_error(client.get(f"/api/clips/{clip_id}/scenes"), 409, "conflict")


def test_patch_rejects_scenes_that_do_not_cover_the_clip(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)

    def patch(scenes: list[dict[str, Any]]) -> Any:
        return client.patch(f"/api/clips/{clip_id}", json={"scene_reframes": scenes})

    gap = assert_error(
        patch([scene(10, 11), scene(11.5, 12.5)]), 422, "validation_error"
    )
    late = assert_error(patch([scene(10.5, 12.5)]), 422, "validation_error")
    short = assert_error(patch([scene(10, 12)]), 422, "validation_error")
    assert "does not start where the scene before it ends (11)" in gap
    assert "not at the clip's start (10)" in late
    assert "not at the clip's end (12.5)" in short
    assert_error(patch([scene(11, 10)]), 422, "validation_error")
    assert_error(patch([scene(10, 12.5, mode="zoom")]), 422, "validation_error")
    with Session(api_engine) as session:
        assert session.get_one(ClipRow, clip_id).scene_reframes == []


def test_track_follows_a_box_through_a_scene_of_the_clip(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    add_work(api_engine, project_id, sample_mp4)
    seed = {"t": 11.0, "x": 0.25, "y": 0.25, "width": 0.125, "height": 0.25}

    response = client.post(
        f"/api/clips/{clip_id}/scenes/track",
        json={"start": 10.5, "end": 12.5, "seed": seed},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["seed"] == seed
    times = [point["t"] for point in body["keyframes"]]
    assert times[0] == 10.5 and times[-1] == 12.4
    assert times == sorted(times)
    assert all(0 <= point["x"] <= 1 for point in body["keyframes"])


def test_track_rejects_a_scene_outside_the_clip_or_a_seed_outside_it(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    add_work(api_engine, project_id, sample_mp4)
    url = f"/api/clips/{clip_id}/scenes/track"
    seed = {"t": 11.0, "x": 0.5, "y": 0.5, "width": 0, "height": 0}

    outside = client.post(url, json={"start": 9.0, "end": 12.0, "seed": seed})
    late_seed = {**seed, "t": 12.4}
    missed = client.post(url, json={"start": 10.0, "end": 12.0, "seed": late_seed})
    empty = client.post(url, json={"start": 11.0, "end": 11.0, "seed": seed})
    unknown = client.post(
        "/api/clips/999/scenes/track", json={"start": 10, "end": 12, "seed": seed}
    )

    message = assert_error(outside, 422, "validation_error")
    assert "inside the clip" in message
    assert "inside the scene" in assert_error(missed, 422, "validation_error")
    assert_error(empty, 422, "validation_error")
    assert_error(unknown, 404, "not_found")
