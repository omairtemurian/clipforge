"""Tests of the brand vocabulary endpoints: GET/PUT /vocabulary and
POST /projects/{id}/replace-everywhere."""

from pathlib import Path
from typing import Any

from apihelpers import assert_error
from clipforge.api.app import create_app
from clipforge.models import Transcript
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine


def replace(client: TestClient, project_id: int, **body: object) -> Any:
    return client.post(f"/api/projects/{project_id}/replace-everywhere", json=body)


def test_the_vocabulary_is_empty_then_saved(data_dir: Path) -> None:
    saved = {"terms": ["Kubernetes"], "corrections": {"cuber netes": "Kubernetes"}}
    with TestClient(create_app(run_worker=False)) as client:
        assert client.get("/api/vocabulary").json() == {"terms": [], "corrections": {}}

        put = client.put("/api/vocabulary", json=saved)
        got = client.get("/api/vocabulary")

    assert put.status_code == 200 and put.json() == saved
    assert got.json() == saved


def test_an_invalid_vocabulary_is_422_and_a_broken_file_409(data_dir: Path) -> None:
    with TestClient(create_app(run_worker=False)) as client:
        assert_error(
            client.put("/api/vocabulary", json={"terms": [""]}),
            422,
            "validation_error",
        )
        (data_dir / "vocabulary.json").write_text("{")
        assert_error(client.get("/api/vocabulary"), 409, "conflict")


def test_replace_everywhere_updates_the_transcript_and_the_clips(
    data_dir: Path, sample_mp4: Path
) -> None:
    with TestClient(create_app(run_worker=False)) as client:
        engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
        project_id = add_project(engine)
        work = add_work(engine, project_id, sample_mp4)
        clip_id = add_clip(engine, project_id, "candidate", 80, title="Yoga night")
        other = add_clip(engine, project_id, "rendered", 70, title="More YOGA")

        response = replace(client, project_id, find="yoga", replace="Yoga Flow")

        clips = {
            c["id"]: c for c in client.get(f"/api/projects/{project_id}/clips").json()
        }
    assert response.status_code == 200
    assert response.json() == {"transcript_matches": 1, "clips_changed": 2}
    transcript = Transcript.model_validate_json((work / "transcript.json").read_text())
    assert "So, I tried Yoga Flow." in [s.text for s in transcript.segments]
    assert clips[clip_id]["title"] == "Yoga Flow night"
    assert clips[other]["title"] == "More Yoga Flow"


def test_remember_saves_the_change_as_a_correction(data_dir: Path) -> None:
    with TestClient(create_app(run_worker=False)) as client:
        engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
        project_id = add_project(engine)
        client.put(
            "/api/vocabulary",
            json={"terms": ["Yoga"], "corrections": {"YOGA": "Yoga", "x": "Y"}},
        )

        kept = replace(client, project_id, find="pie", replace="Pie")
        saved = client.get("/api/vocabulary").json()
        forgotten = replace(client, project_id, find="yoga", replace="Yoga Flow")
        replace(client, project_id, find="yoga", replace="Yoga Flow", remember=True)
        remembered = client.get("/api/vocabulary").json()

    assert kept.status_code == forgotten.status_code == 200
    assert saved["corrections"] == {"YOGA": "Yoga", "x": "Y"}
    assert remembered == {
        "terms": ["Yoga"],
        "corrections": {"x": "Y", "yoga": "Yoga Flow"},
    }


def test_replace_everywhere_errors(data_dir: Path) -> None:
    with TestClient(create_app(run_worker=False)) as client:
        assert_error(replace(client, 99, find="a", replace="b"), 404, "not_found")
        engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
        project_id = add_project(engine)
        assert_error(
            replace(client, project_id, find="", replace="b"), 422, "validation_error"
        )
