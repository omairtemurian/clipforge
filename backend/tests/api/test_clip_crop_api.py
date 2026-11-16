"""Tests of the crop tool's endpoint (GET /clips/{id}/crop) and of saving a
clip's framing (PATCH /clips/{id})."""

from pathlib import Path

from apihelpers import assert_error
from clipforge.db import ClipRow
from clipforge.models import CropTrack, SignalList
from clipforge.pipeline.step import SIGNALS, write_json
from fastapi.testclient import TestClient
from seed import add_clip, add_plan, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


def test_the_crop_track_is_the_planned_fill_window_in_an_aspect(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    work = add_work(api_engine, project_id, sample_mp4)
    add_plan(work, clip_id)
    write_json(work / SIGNALS, SignalList([]))

    response = client.get(f"/api/clips/{clip_id}/crop")
    square = client.get(f"/api/clips/{clip_id}/crop", params={"aspect": "1:1"})

    assert response.status_code == 200
    track = CropTrack.model_validate(response.json())
    assert (track.aspect, track.frame_width, track.frame_height) == ("9:16", 1280, 720)
    assert (track.width, track.height, track.y) == (404, 720, 0)
    assert track.times[0] == 10.0
    assert len(track.xs) == len(track.times)
    assert square.status_code == 200
    assert (square.json()["width"], square.json()["aspect"]) == (720, "1:1")


def test_the_crop_track_needs_a_clip_and_its_plan(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)

    assert_error(client.get("/api/clips/999/crop"), 404, "not_found")
    assert_error(client.get(f"/api/clips/{clip_id}/crop"), 409, "conflict")
    add_work(api_engine, project_id, sample_mp4)
    message = assert_error(client.get(f"/api/clips/{clip_id}/crop"), 409, "conflict")
    assert f"crop_{clip_id}.json" in message
    bad = client.get(f"/api/clips/{clip_id}/crop", params={"aspect": "1:9"})
    assert_error(bad, 422, "validation_error")


def test_patch_replaces_the_framing(client: TestClient, api_engine: Engine) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    framing = {
        "aspect": "1:1",
        "background": "black",
        "scale": 0.5,
        "points": [{"t": 11.0, "x": 0.25, "y": 0.5}],
        "tracker": False,
        "facecam": {"x": 0.75, "y": 0.5, "width": 0.25, "height": 0.5},
    }

    response = client.patch(f"/api/clips/{clip_id}", json={"framing": framing})
    client.patch(f"/api/clips/{clip_id}", json={"title": "Kept"})

    assert response.status_code == 200
    assert response.json()["framing"] == framing
    with Session(api_engine) as session:
        stored = session.get_one(ClipRow, clip_id).to_model()
    assert stored.framing.model_dump() == framing
    client.patch(f"/api/clips/{clip_id}", json={"framing": {"tracker": False}})
    with Session(api_engine) as session:
        stored = session.get_one(ClipRow, clip_id).to_model()
    assert stored.framing.points == []
    assert stored.framing.aspect is None
    assert stored.framing.facecam is None
    outside = {"x": 0.8, "y": 0.0, "width": 0.25, "height": 0.5}
    past_edge = client.patch(
        f"/api/clips/{clip_id}", json={"framing": {"facecam": outside}}
    )
    assert_error(past_edge, 422, "validation_error")
    too_small = client.patch(f"/api/clips/{clip_id}", json={"framing": {"scale": 0.1}})
    assert_error(too_small, 422, "validation_error")
