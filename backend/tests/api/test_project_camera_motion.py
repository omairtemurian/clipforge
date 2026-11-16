"""PUT /projects/{id}/camera-motion: the camera motion of the project's
crop windows (steering: calmer auto-track), saved and applied to the crop
plans of its clips."""

from pathlib import Path

from apihelpers import assert_error
from clipforge.clip_layouts import load_plan
from clipforge.models import CropPlan, FaceBox, SignalList
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, crop_path, plan_crop
from clipforge.pipeline.step import SIGNALS, write_json
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine


def face(center_x: float) -> FaceBox:
    """A 100 px face centered at center_x."""
    return FaceBox(x=center_x - 50, y=250, width=100, height=100, score=0.9)


def add_walking_plan(work: Path, clip_id: int) -> CropPlan:
    """Write the fast 9:16 crop plan of clip clip_id, 10 to 14 s, of a face
    that walks from x 300 to 1000 of the 1280x720 video; return it."""
    times = sample_times(10.0, 14.0)
    faces = [[face(300 + 700 * k / len(times))] for k in range(len(times))]
    span = ClipSpan(clip_id, 10.0, 14.0)
    plan = plan_crop(span, "9:16", (1280, 720), faces, [], camera_motion="fast")
    write_json(crop_path(work, clip_id), plan)
    return plan


def test_the_motion_is_saved_in_the_projects_settings(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)

    response = client.put(
        f"/api/projects/{project_id}/camera-motion", json={"camera_motion": "fast"}
    )

    assert response.status_code == 200
    assert response.json()["clip_ids"] == []
    assert response.json()["project"]["settings"]["camera_motion"] == "fast"
    stored = client.get(f"/api/projects/{project_id}").json()
    assert stored["settings"]["camera_motion"] == "fast"


def test_the_clips_windows_are_planned_again_with_the_motion(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "rendered", 80)
    work = add_work(api_engine, project_id, sample_mp4)
    fast = add_walking_plan(work, clip_id)
    write_json(work / SIGNALS, SignalList([]))

    response = client.put(
        f"/api/projects/{project_id}/camera-motion", json={"camera_motion": "calm"}
    )

    assert response.status_code == 200
    assert response.json()["clip_ids"] == [clip_id]
    calm = load_plan(work, clip_id)
    assert calm.camera_motion == "calm"
    assert [k.faces for k in calm.keyframes] == [k.faces for k in fast.keyframes]
    assert calm.layout == fast.layout
    # The calm window rests before it moves, the fast one sets off at once.
    assert calm.keyframes[0].x == calm.keyframes[5].x
    assert fast.keyframes[0].x != fast.keyframes[5].x

    again = client.put(
        f"/api/projects/{project_id}/camera-motion", json={"camera_motion": "fast"}
    )

    assert again.status_code == 200
    assert load_plan(work, clip_id) == fast


def test_a_bad_motion_or_project_is_refused(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)

    bad = client.put(
        f"/api/projects/{project_id}/camera-motion", json={"camera_motion": "slow"}
    )
    assert_error(bad, 422, "validation_error")
    missing = client.put(
        "/api/projects/999/camera-motion", json={"camera_motion": "calm"}
    )
    assert_error(missing, 404, "not_found")
