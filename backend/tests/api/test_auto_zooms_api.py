"""Tests of GET /clips/{id}/auto-zooms, the editor's auto zoom (TASK-23),
and of saving a clip's zoom with PATCH."""

from pathlib import Path

from apihelpers import assert_error
from builders import FIXTURE_LAUGHS
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import ProcessingSettings, SignalList
from clipforge.pipeline.step import SIGNALS, write_json
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


def seed_clip(api_engine: Engine, sample_mp4: Path, **changes: object) -> int:
    """Add a project processed from the fixture (with its laughs) and a clip
    of it that emphasizes "floor"; return the clip's id."""
    project_id = add_project(api_engine)
    work = add_work(api_engine, project_id, sample_mp4)
    write_json(work / SIGNALS, SignalList(list(FIXTURE_LAUGHS)))
    return add_clip(
        api_engine, project_id, "candidate", 80, emphasis_words=["floor"], **changes
    )


def test_auto_zooms_of_the_saved_clip_leave_it_unchanged(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    clip_id = seed_clip(api_engine, sample_mp4, start=0.5, end=12.0)

    response = client.get(f"/api/clips/{clip_id}/auto-zooms")

    # The new sentences after the cuts at 3.02-3.33 s and 6.17-6.63 s; the
    # one at 10.98 s is too close to the end.
    assert response.status_code == 200
    assert response.json() == [
        {"t": 3.13, "scale": 1.0},
        {"t": 3.33, "scale": 1.12},
        {"t": 5.33, "scale": 1.12},
        {"t": 5.83, "scale": 1.0},
        {"t": 6.43, "scale": 1.0},
        {"t": 6.63, "scale": 1.12},
        {"t": 8.63, "scale": 1.12},
        {"t": 9.13, "scale": 1.0},
    ]
    clip = client.get(f"/api/clips/{clip_id}").json()
    assert (clip["auto_zoom"], clip["zoom_keyframes"]) == (False, [])


def test_auto_zooms_of_an_unsaved_span_prefer_the_emphasis_words(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    clip_id = seed_clip(api_engine, sample_mp4)
    with Session(api_engine) as session:
        project = session.get_one(ProjectRow, 1)
        project.settings = ProcessingSettings(auto_cut_min_pause_s=0.6)
        session.add(project)
        session.commit()

    response = client.get(
        f"/api/clips/{clip_id}/auto-zooms", params={"start": 5, "end": 18}
    )

    # "floor?" at 12.99 s wins over the laugh at 14.16 s, 1.17 s later.
    punches = [(k["t"], k["scale"]) for k in response.json()[1::4]]
    assert punches == [(6.63, 1.12), (12.99, 1.15)]


def test_auto_zoom_errors(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    clip_id = seed_clip(api_engine, sample_mp4)
    url = f"/api/clips/{clip_id}/auto-zooms"

    assert_error(client.get("/api/clips/42/auto-zooms"), 404, "not_found")
    for params in ({"start": 12, "end": 11}, {"end": 61}, {"start": -1}):
        assert_error(client.get(url, params=params), 422, "validation_error")
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    other = add_clip(api_engine, project_id, "candidate", 80)
    missing = client.get(f"/api/clips/{other}/auto-zooms")
    assert "signals.json" in assert_error(missing, 409, "conflict")


def test_patch_saves_auto_zoom_and_its_keyframes_in_time_order(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    keyframes = [{"t": 11.2, "scale": 1.0}, {"t": 10.5, "scale": 1.12}]

    body = {"auto_zoom": True, "zoom_keyframes": keyframes}
    response = client.patch(f"/api/clips/{clip_id}", json=body)

    assert response.status_code == 200
    assert response.json()["zoom_keyframes"] == keyframes[::-1]
    with Session(api_engine) as session:
        row = session.get_one(ClipRow, clip_id)
        assert row.auto_zoom
        assert [(k.t, k.scale) for k in row.zoom_keyframes] == [
            (10.5, 1.12),
            (11.2, 1.0),
        ]
    client.patch(f"/api/clips/{clip_id}", json={"auto_zoom": False})
    clip = client.get(f"/api/clips/{clip_id}").json()
    assert (clip["auto_zoom"], len(clip["zoom_keyframes"])) == (False, 2)
    too_much = {"zoom_keyframes": [{"t": 10.5, "scale": 2.5}]}
    assert_error(
        client.patch(f"/api/clips/{clip_id}", json=too_much), 422, "validation_error"
    )
