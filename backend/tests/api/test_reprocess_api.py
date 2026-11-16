"""POST /projects/{id}/reprocess: a failed project's process job is queued
again (its attempts, step and error cleared) and resumes after the steps it
finished."""

from pathlib import Path

from apihelpers import assert_error
from clipforge.db import JobRow, ProjectRow
from clipforge.models import JobStatus
from clipforge.pipeline.step import job_dir, mark_done, step_done
from fastapi.testclient import TestClient
from seed import add_job, add_project
from sqlalchemy import Engine
from sqlmodel import Session


def failed_project(engine: Engine, status: JobStatus = "failed") -> tuple[int, int]:
    """Add a project with status whose process job failed at transcribe after
    two attempts; return their ids."""
    project_id = add_project(engine)
    job_id = add_job(engine, project_id, "failed", "transcribe", 0.4)
    with Session(engine) as session:
        project = session.get_one(ProjectRow, project_id)
        project.status = status
        job = session.get_one(JobRow, job_id)
        job.error, job.attempts, job.overall_progress = "whisper crashed", 2, 0.3
        session.add_all([project, job])
        session.commit()
    return project_id, job_id


def test_a_failed_project_is_queued_again_and_keeps_its_finished_steps(
    client: TestClient, api_engine: Engine
) -> None:
    project_id, job_id = failed_project(api_engine)
    work: Path = job_dir(job_id)
    work.mkdir(parents=True)
    mark_done(work, "ingest")

    response = client.post(f"/api/projects/{project_id}/reprocess")

    assert response.status_code == 202
    job = response.json()
    assert (job["id"], job["kind"], job["status"]) == (job_id, "process", "queued")
    assert (job["step"], job["progress"], job["error"]) == ("", 0.0, None)
    assert (job["attempts"], job["overall_progress"]) == (0, 0.0)
    project = client.get(f"/api/projects/{project_id}").json()
    assert (project["status"], project["overall_progress"]) == ("queued", 0.0)
    assert step_done(work, "ingest")


def test_only_a_failed_project_can_be_processed_again(
    client: TestClient, api_engine: Engine
) -> None:
    for status in ("done", "queued", "running"):
        project_id, _ = failed_project(api_engine, status)
        response = client.post(f"/api/projects/{project_id}/reprocess")
        assert_error(response, 409, "conflict")


def test_a_project_without_a_process_job_or_archived_is_refused(
    client: TestClient, api_engine: Engine
) -> None:
    lonely = add_project(api_engine)
    archived, _ = failed_project(api_engine)
    with Session(api_engine) as session:
        for project_id, field in ((lonely, "status"), (archived, "archived_at")):
            row = session.get_one(ProjectRow, project_id)
            if field == "status":
                row.status = "failed"
            else:
                row.archived_at = row.created_at
            session.add(row)
        session.commit()

    for project_id in (lonely, archived):
        response = client.post(f"/api/projects/{project_id}/reprocess")
        assert_error(response, 409, "conflict")


def test_reprocess_of_a_missing_project_is_404(client: TestClient) -> None:
    assert_error(client.post("/api/projects/99/reprocess"), 404, "not_found")
