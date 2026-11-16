"""Tests of the media endpoint (HTTP Range) and the API's JSON errors."""

from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge.api.app import create_app
from clipforge.db import JobRow
from clipforge.pipeline.step import SOURCE, THUMB, job_dir
from fastapi.testclient import TestClient
from seed import add_project
from sqlalchemy import Engine
from sqlmodel import Session, select

SOURCE_BYTES = bytes(range(256)) * 40


@pytest.fixture
def project_id(client: TestClient, api_engine: Engine) -> int:
    """A project whose process job has ingested SOURCE_BYTES."""
    project_id = add_project(api_engine)
    with Session(api_engine) as session:
        job = JobRow(
            project_id=project_id, kind="process", step="", log_path="", status="done"
        )
        session.add(job)
        session.commit()
        assert job.id is not None
        work = job_dir(job.id)
    work.mkdir(parents=True)
    (work / SOURCE).write_bytes(SOURCE_BYTES)
    return project_id


def test_source_is_served_whole_and_announces_ranges(
    client: TestClient, project_id: int
) -> None:
    response = client.get(f"/api/media/{project_id}/source")

    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == SOURCE_BYTES


def test_a_range_request_gets_206_and_the_bytes_asked_for(
    client: TestClient, project_id: int
) -> None:
    size = len(SOURCE_BYTES)
    response = client.get(
        f"/api/media/{project_id}/source", headers={"Range": "bytes=100-299"}
    )

    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 100-299/{size}"
    assert response.headers["content-length"] == "200"
    assert response.content == SOURCE_BYTES[100:300]


def test_open_ended_and_suffix_ranges(client: TestClient, project_id: int) -> None:
    size = len(SOURCE_BYTES)
    url = f"/api/media/{project_id}/source"

    tail = client.get(url, headers={"Range": f"bytes={size - 10}-"})
    last = client.get(url, headers={"Range": "bytes=-50"})

    assert tail.status_code == 206
    assert tail.headers["content-range"] == f"bytes {size - 10}-{size - 1}/{size}"
    assert tail.content == SOURCE_BYTES[-10:]
    assert last.status_code == 206
    assert last.headers["content-range"] == f"bytes {size - 50}-{size - 1}/{size}"
    assert last.content == SOURCE_BYTES[-50:]


def test_a_range_past_the_end_is_416(client: TestClient, project_id: int) -> None:
    size = len(SOURCE_BYTES)
    response = client.get(
        f"/api/media/{project_id}/source", headers={"Range": f"bytes={size}-"}
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{size}"


def test_source_of_an_unknown_project_is_404(client: TestClient) -> None:
    assert_error(client.get("/api/media/99/source"), 404, "not_found")


def test_source_before_ingest_is_404(client: TestClient, api_engine: Engine) -> None:
    waiting = add_project(api_engine)
    assert "no process job" in assert_error(
        client.get(f"/api/media/{waiting}/source"), 404, "not_found"
    )
    with Session(api_engine) as session:
        session.add(JobRow(project_id=waiting, kind="process", step="", log_path=""))
        session.commit()

    message = assert_error(client.get(f"/api/media/{waiting}/source"), 404, "not_found")
    assert "not ready" in message


def test_thumbnail_is_served_as_jpeg(
    client: TestClient, api_engine: Engine, project_id: int
) -> None:
    missing = client.get(f"/api/media/{project_id}/thumbnail")
    with Session(api_engine) as session:
        job = session.exec(select(JobRow).where(JobRow.project_id == project_id)).one()
        assert job.id is not None
        (job_dir(job.id) / THUMB).write_bytes(b"\xff\xd8jpeg")

    response = client.get(f"/api/media/{project_id}/thumbnail")

    assert "not ready" in assert_error(missing, 404, "not_found")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"\xff\xd8jpeg"


def test_thumbnail_of_an_unknown_project_is_404(client: TestClient) -> None:
    assert_error(client.get("/api/media/99/thumbnail"), 404, "not_found")


def test_source_with_a_bad_id_is_422(client: TestClient) -> None:
    assert_error(client.get("/api/media/abc/source"), 422, "validation_error")


def test_unknown_path_and_wrong_method_are_json_errors(client: TestClient) -> None:
    assert_error(client.get("/api/nothing"), 404, "not_found")
    assert_error(client.put("/api/projects"), 405, "method_not_allowed")


def test_an_unhandled_exception_is_a_500_json_without_a_traceback(
    data_dir: Path,
) -> None:
    app = create_app(run_worker=False)

    @app.get("/api/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/boom")

    message = assert_error(response, 500, "internal_error")
    assert "secret" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in message
