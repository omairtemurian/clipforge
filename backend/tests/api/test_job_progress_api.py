"""Tests of the overall progress and ETA over the API (steering 2026-11-02):
GET /projects, /projects/{id}/jobs and the job events carry them, and
opening a finished project clears its "New" badge."""

import json

from clipforge.db import JobRow, ProjectRow
from fastapi.testclient import TestClient
from seed import add_job, add_project
from sqlalchemy import Engine
from sqlmodel import Session


def set_progress(engine: Engine, project_id: int, job_id: int) -> None:
    """Give the job and its project the progress the worker would save."""
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        project = session.get(ProjectRow, project_id)
        assert job is not None and project is not None
        job.overall_progress = project.overall_progress = 0.48
        job.eta_seconds = project.eta_seconds = 300.0
        project.status = "running"
        session.commit()


def test_projects_and_jobs_carry_the_progress_and_eta(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    job_id = add_job(api_engine, project_id, "running", "transcribe", 0.4)
    set_progress(api_engine, project_id, job_id)

    [project] = client.get("/api/projects").json()
    [job] = client.get(f"/api/projects/{project_id}/jobs").json()
    event = read_job_event(client, job_id)

    assert (project["overall_progress"], project["eta_seconds"]) == (0.48, 300.0)
    assert (job["overall_progress"], job["eta_seconds"]) == (0.48, 300.0)
    assert (event["overall_progress"], event["eta_seconds"]) == (0.48, 300.0)
    assert client.get(f"/api/projects/{project_id}").json()["eta_seconds"] == 300.0


def read_job_event(client: TestClient, job_id: int) -> dict:  # type: ignore[type-arg]
    """Return the first event of a job's stream (the stream is read to its
    end, so the job must be over: it is set done first)."""
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        job = session.get(JobRow, job_id)
        assert job is not None
        job.status = "done"
        session.commit()
    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        line = next(x for x in response.iter_lines() if x.startswith("data: "))
    event: dict = json.loads(line.removeprefix("data: "))  # type: ignore[type-arg]
    return event


def test_a_new_project_is_unopened_until_it_is_opened(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    assert client.get(f"/api/projects/{project_id}").json()["opened_at"] is None

    opened = client.post(f"/api/projects/{project_id}/open").json()
    again = client.post(f"/api/projects/{project_id}/open").json()

    assert opened["opened_at"] is not None
    assert again["opened_at"] == opened["opened_at"]
    assert client.get("/api/projects").json()[0]["opened_at"] == opened["opened_at"]


def test_opening_a_missing_project_is_404(client: TestClient) -> None:
    assert client.post("/api/projects/99/open").status_code == 404
