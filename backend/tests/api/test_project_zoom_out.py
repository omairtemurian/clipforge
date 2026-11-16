"""PUT /projects/{id}/zoom-out: the project's zoom-out moments intensity
(TASK-198b), saved and applied to the clips without manual scenes."""

from pathlib import Path

from apihelpers import assert_error
from clipforge.db import ClipRow
from clipforge.models import SceneReframe, SignalList
from clipforge.pipeline.step import SIGNALS, write_json
from fastapi.testclient import TestClient
from seed import add_clip, add_plan, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


def test_the_intensity_is_saved_in_the_projects_settings(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)

    response = client.put(
        f"/api/projects/{project_id}/zoom-out", json={"intensity": "frequent"}
    )

    assert response.status_code == 200
    assert response.json()["clip_ids"] == []
    assert response.json()["project"]["settings"]["zoom_out_moments"] == "frequent"
    stored = client.get(f"/api/projects/{project_id}").json()
    assert stored["settings"]["zoom_out_moments"] == "frequent"


def test_the_clips_without_manual_scenes_are_planned_again(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    scenes = [
        SceneReframe(start=10.0, end=11.0),
        SceneReframe(start=11.0, end=12.5, layout="square_blur"),
    ]
    clip_id = add_clip(api_engine, project_id, "rendered", 80, scene_reframes=scenes)
    work = add_work(api_engine, project_id, sample_mp4)
    add_plan(work, clip_id)
    write_json(work / SIGNALS, SignalList([]))

    response = client.put(
        f"/api/projects/{project_id}/zoom-out", json={"intensity": "off"}
    )

    assert response.status_code == 200
    assert response.json()["clip_ids"] == [clip_id]
    with Session(api_engine) as session:
        row = session.get_one(ClipRow, clip_id)
        assert row.scene_reframes == []


def test_a_bad_intensity_or_project_is_refused(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)

    bad = client.put(f"/api/projects/{project_id}/zoom-out", json={"intensity": "max"})
    assert_error(bad, 422, "validation_error")
    missing = client.put("/api/projects/999/zoom-out", json={"intensity": "off"})
    assert_error(missing, 404, "not_found")
