"""Tests of the job endpoints: a project's jobs, one job and the SSE events."""

import json
import threading
import time

import pytest
from apihelpers import assert_error
from clipforge.api import jobs as api_jobs
from clipforge.db import JobRow
from clipforge.models import Job
from fastapi.testclient import TestClient
from seed import add_job, add_project
from sqlalchemy import Engine
from sqlmodel import Session


def set_job(engine: Engine, job_id: int, **fields: object) -> None:
    """Update fields of a job row, as the worker does."""
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        assert job is not None
        for name, value in fields.items():
            setattr(job, name, value)
        session.commit()


def read_events(client: TestClient, job_id: int) -> list[dict]:  # type: ignore[type-arg]
    """Follow a job's event stream to its end and return the events' data."""
    events = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line.removeprefix("data: ")))
    return events


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_jobs, "POLL_INTERVAL", 0.02)


def test_a_projects_jobs_are_listed_newest_first(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    other = add_project(api_engine)
    first = add_job(api_engine, project_id, "done")
    add_job(api_engine, other, "queued")
    second = add_job(api_engine, project_id, "running", "curate", 0.4)

    response = client.get(f"/api/projects/{project_id}/jobs")

    assert response.status_code == 200
    jobs = [Job.model_validate(item) for item in response.json()]
    assert [job.id for job in jobs] == [second, first]
    assert (jobs[0].kind, jobs[0].step, jobs[0].progress) == ("process", "curate", 0.4)


def test_a_project_without_jobs_has_an_empty_list(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)

    assert client.get(f"/api/projects/{project_id}/jobs").json() == []


def test_a_job_is_returned_with_its_error(
    client: TestClient, api_engine: Engine
) -> None:
    job_id = add_job(api_engine, add_project(api_engine), "queued")
    set_job(api_engine, job_id, status="failed", error="boom", step="ingest")

    body = client.get(f"/api/jobs/{job_id}").json()

    assert body["id"] == job_id
    assert (body["status"], body["error"], body["step"]) == ("failed", "boom", "ingest")


def test_a_missing_project_or_job_is_404(client: TestClient) -> None:
    assert_error(client.get("/api/projects/99/jobs"), 404, "not_found")
    assert_error(client.get("/api/jobs/99"), 404, "not_found")
    assert_error(client.get("/api/jobs/99/events"), 404, "not_found")


def test_events_of_a_finished_job_are_one_terminal_event(
    client: TestClient, api_engine: Engine
) -> None:
    job_id = add_job(api_engine, add_project(api_engine), "done", "render", 1.0)

    assert read_events(client, job_id) == [
        {
            "step": "render",
            "progress": 1.0,
            "status": "done",
            "message": "Done.",
            "overall_progress": 0.0,
            "eta_seconds": None,
        }
    ]


def test_events_follow_a_job_to_its_terminal_status(
    client: TestClient, api_engine: Engine
) -> None:
    job_id = add_job(api_engine, add_project(api_engine), "queued")

    def work() -> None:
        for step, progress in (("ingest", 0.1), ("curate", 0.5), ("render", 0.9)):
            time.sleep(0.15)
            set_job(api_engine, job_id, status="running", step=step, progress=progress)
        time.sleep(0.15)
        set_job(api_engine, job_id, status="done", progress=1.0)

    worker = threading.Thread(target=work)
    worker.start()
    try:
        events = read_events(client, job_id)
    finally:
        worker.join()

    assert len(events) >= 2
    assert events[0]["status"] == "queued"
    assert events[-1] == {
        "step": "render",
        "progress": 1.0,
        "status": "done",
        "message": "Done.",
        "overall_progress": 0.0,
        "eta_seconds": None,
    }
    assert [e["status"] for e in events].count("done") == 1
    progress = [e["progress"] for e in events]
    assert progress == sorted(progress)
    assert all(
        set(e)
        == {
            "step",
            "progress",
            "status",
            "message",
            "overall_progress",
            "eta_seconds",
        }
        for e in events
    )
    assert {"step": "curate", "progress": 0.5} in [
        {"step": e["step"], "progress": e["progress"]} for e in events
    ]


def test_a_failed_job_ends_the_stream_with_its_error(
    client: TestClient, api_engine: Engine
) -> None:
    job_id = add_job(api_engine, add_project(api_engine), "running", "ingest", 0.2)

    def fail() -> None:
        time.sleep(0.15)
        set_job(api_engine, job_id, status="failed", error="download failed")

    worker = threading.Thread(target=fail)
    worker.start()
    try:
        events = read_events(client, job_id)
    finally:
        worker.join()

    assert events[0]["message"] == "Running ingest."
    assert events[-1]["status"] == "failed"
    assert events[-1]["message"] == "download failed"


def test_unchanged_state_is_not_repeated(
    client: TestClient, api_engine: Engine
) -> None:
    job_id = add_job(api_engine, add_project(api_engine), "running", "ingest", 0.2)

    def finish() -> None:
        time.sleep(0.3)
        set_job(api_engine, job_id, status="done")

    worker = threading.Thread(target=finish)
    worker.start()
    try:
        events = read_events(client, job_id)
    finally:
        worker.join()

    assert [e["status"] for e in events] == ["running", "done"]
