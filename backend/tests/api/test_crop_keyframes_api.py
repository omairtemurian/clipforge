"""Tests of manual reframe keyframes over the API: PUT and DELETE
/clips/{id}/crop-keyframes (api/clip_keyframes, pipeline/keyframes)."""

from pathlib import Path

from apihelpers import assert_error
from builders import cut
from clipforge.db import ClipRow
from clipforge.models import CropPoint, SceneReframe, SignalList
from clipforge.pipeline.step import SIGNALS, write_json
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


def keys_url(clip_id: int) -> str:
    """The crop keyframes URL of clip clip_id."""
    return f"/api/clips/{clip_id}/crop-keyframes"


def test_a_keyframe_splits_the_clip_at_its_cuts_and_fixes_its_scene(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    work = add_work(api_engine, project_id, sample_mp4)
    write_json(work / SIGNALS, SignalList([cut(11.0)]))

    first = client.put(keys_url(clip_id), json={"t": 11.5, "x": 0.25, "y": 0.5})
    moved = client.put(
        keys_url(clip_id), json={"t": 11.55, "x": 0.75, "y": 0.4, "scale": 0.5}
    )
    second = client.put(keys_url(clip_id), json={"t": 12.0, "x": 0.5, "y": 0.5})

    assert first.status_code == moved.status_code == second.status_code == 200
    scenes = second.json()["scene_reframes"]
    assert [(s["start"], s["end"], s["mode"]) for s in scenes] == [
        (10.0, 11.0, "auto"),
        (11.0, 12.5, "fixed"),
    ]
    assert scenes[1]["scale"] == 0.5
    assert scenes[1]["crop_keyframes"] == [
        {"t": 11.55, "x": 0.75, "y": 0.4},
        {"t": 12.0, "x": 0.5, "y": 0.5},
    ]
    with Session(api_engine) as session:
        stored = session.get_one(ClipRow, clip_id).to_model().scene_reframes
    assert [key.t for key in stored[1].crop_keyframes] == [11.55, 12.0]


def test_deleting_a_keyframe_keeps_the_others(
    client: TestClient, api_engine: Engine
) -> None:
    keys = [CropPoint(t=10.5, x=0.2, y=0.5), CropPoint(t=12.0, x=0.8, y=0.5)]
    scenes = [SceneReframe(start=10.0, end=12.5, mode="fixed", crop_keyframes=keys)]
    clip_id = add_clip(
        api_engine, add_project(api_engine), "candidate", 80, scene_reframes=scenes
    )

    response = client.delete(keys_url(clip_id), params={"t": 10.55})

    assert response.status_code == 200
    assert response.json()["scene_reframes"][0]["crop_keyframes"] == [
        keys[1].model_dump()
    ]
    missing = client.delete(keys_url(clip_id), params={"t": 10.5})
    assert "no crop keyframe at 10.5" in assert_error(missing, 404, "not_found")


def test_keyframes_need_a_fill_scene_inside_the_clip(
    client: TestClient, api_engine: Engine
) -> None:
    scenes = [
        SceneReframe(start=10.0, end=11.0, layout="fit"),
        SceneReframe(start=11.0, end=12.5),
    ]
    clip_id = add_clip(
        api_engine, add_project(api_engine), "candidate", 80, scene_reframes=scenes
    )

    fit = client.put(keys_url(clip_id), json={"t": 10.5, "x": 0.5, "y": 0.5})
    outside = client.put(keys_url(clip_id), json={"t": 13.0, "x": 0.5, "y": 0.5})
    small = client.put(
        keys_url(clip_id), json={"t": 12, "x": 0.5, "y": 0.5, "scale": 0.1}
    )

    assert "fit layout" in assert_error(fit, 422, "validation_error")
    assert "not inside the clip" in assert_error(outside, 422, "validation_error")
    assert_error(small, 422, "validation_error")
    with Session(api_engine) as session:
        assert session.get_one(ClipRow, clip_id).to_model().scene_reframes == scenes


def test_keyframes_need_the_clip_its_signals_and_no_render(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    rendering = add_clip(api_engine, project_id, "rendering", 80)
    body = {"t": 11.0, "x": 0.5, "y": 0.5}

    assert_error(client.put(keys_url(999), json=body), 404, "not_found")
    assert_error(client.put(keys_url(clip_id), json=body), 409, "conflict")
    add_work(api_engine, project_id, sample_mp4)
    assert_error(client.put(keys_url(clip_id), json=body), 409, "conflict")
    assert_error(client.put(keys_url(rendering), json=body), 409, "conflict")
    assert_error(
        client.delete(keys_url(clip_id), params={"t": -1}), 422, "validation_error"
    )
