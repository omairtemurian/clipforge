"""Tests of GET /clips/{id}/auto-cuts, the editor's auto cut (TASK-27)."""

from pathlib import Path

from apihelpers import assert_error
from builders import FIXTURE_LAUGHS
from clipforge.db import ProjectRow
from clipforge.models import ProcessingSettings, SignalList
from clipforge.pipeline.step import SIGNALS, write_json
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


def seed_clip(api_engine: Engine, sample_mp4: Path, **changes: object) -> int:
    """Add a project processed from the fixture (with its laughs) and a clip
    of it; return the clip's id."""
    project_id = add_project(api_engine)
    work = add_work(api_engine, project_id, sample_mp4)
    write_json(work / SIGNALS, SignalList(list(FIXTURE_LAUGHS)))
    return add_clip(api_engine, project_id, "candidate", 80, **changes)


def test_auto_cuts_of_the_saved_clip_leave_it_unchanged(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    clip_id = seed_clip(api_engine, sample_mp4, start=0.5, end=12.0)

    response = client.get(f"/api/clips/{clip_id}/auto-cuts")

    assert response.status_code == 200
    assert response.json() == [
        [3.02, 3.33],
        [6.17, 6.63],
        [7.27, 7.58],
        [10.62, 10.98],
    ]
    assert client.get(f"/api/clips/{clip_id}").json()["cut_ranges"] == []


def test_auto_cuts_of_an_unsaved_span_with_the_project_min_pause(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    clip_id = seed_clip(api_engine, sample_mp4)
    url = f"/api/clips/{clip_id}/auto-cuts"
    with Session(api_engine) as session:
        project = session.get_one(ProjectRow, 1)
        project.settings = ProcessingSettings(auto_cut_min_pause_s=0.6)
        session.add(project)
        session.commit()

    response = client.get(url, params={"start": 5, "end": 12.5})

    # Of 5-12.5 s, only the 0.7 s before "Um," is longer than 0.6 s.
    assert response.json() == [[6.17, 6.63]]


def test_auto_cut_errors(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    clip_id = seed_clip(api_engine, sample_mp4)
    url = f"/api/clips/{clip_id}/auto-cuts"

    assert_error(client.get("/api/clips/42/auto-cuts"), 404, "not_found")
    for params in ({"start": 12, "end": 11}, {"end": 61}, {"start": -1}):
        assert_error(client.get(url, params=params), 422, "validation_error")
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    other = add_clip(api_engine, project_id, "candidate", 80)
    missing = client.get(f"/api/clips/{other}/auto-cuts")
    assert "signals.json" in assert_error(missing, 409, "conflict")
