"""Tests of the project endpoints: create, upload, list, get, delete."""

import json
import time
from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge.api.app import create_app
from clipforge.db import ClipRow, JobRow, ProjectRow
from clipforge.pipeline.render import project_output
from clipforge.pipeline.step import job_dir
from fastapi.testclient import TestClient
from seed import add_clip, add_job, add_project
from sqlalchemy import Engine
from sqlmodel import Session, select

URL = "https://www.youtube.com/watch?v=abc"


def upload(client: TestClient, name: str = "talk.mp4", data: bytes = b"video") -> dict:  # type: ignore[type-arg]
    """Upload a file with default settings and return the project."""
    response = client.post(
        "/api/projects/upload", files={"file": (name, data, "video/mp4")}
    )
    assert response.status_code == 201
    project: dict = response.json()  # type: ignore[type-arg]
    return project


def test_create_project_from_a_url_queues_a_process_job(
    client: TestClient, api_engine: Engine
) -> None:
    response = client.post(
        "/api/projects", json={"url": URL, "settings": {"num_clips": 3}}
    )

    assert response.status_code == 201
    project = response.json()
    assert project["source_url"] == URL
    assert project["status"] == "queued"
    assert project["settings"]["num_clips"] == 3
    with Session(api_engine) as session:
        job = session.exec(select(JobRow)).one()
    assert (job.project_id, job.kind, job.status) == (
        project["id"],
        "process",
        "queued",
    )


def test_create_project_without_settings_uses_the_defaults(client: TestClient) -> None:
    response = client.post("/api/projects", json={"url": URL})

    assert response.status_code == 201
    assert response.json()["settings"]["aspect"] == "9:16"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"url": None},
        {"url": "/videos/talk.mp4"},
        {"url": "ftp://example.com/a.mp4"},
        {"url": URL, "settings": {"num_clips": 0}},
        {"url": URL, "settings": {"genre": "sports"}},
    ],
)
def test_create_project_rejects_an_invalid_body(
    client: TestClient, body: dict[str, object]
) -> None:
    response = client.post("/api/projects", json=body)

    assert_error(response, 422, "validation_error")
    assert client.get("/api/projects").json() == []


@pytest.mark.parametrize(
    "url", ["https://vimeo.com/76979871", "https://cdn.example/talks/big-laugh.mp4"]
)
def test_create_project_accepts_non_youtube_links(client: TestClient, url: str) -> None:
    response = client.post("/api/projects", json={"url": url})

    assert response.status_code == 201
    assert response.json()["source_url"] == url


def test_create_project_rejects_a_site_without_an_extractor(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/projects", json={"url": "https://example.com/talks/big-laugh"}
    )

    message = assert_error(response, 422, "unsupported_source")
    assert message.startswith("example.com is not a supported video site")
    assert client.get("/api/projects").json() == []


def test_upload_saves_the_file_and_queues_a_process_job(
    client: TestClient, api_engine: Engine, data_dir: Path
) -> None:
    settings = json.dumps({"num_clips": 2, "aspect": "1:1"})
    response = client.post(
        "/api/projects/upload",
        files={"file": ("talk.mp4", b"video bytes", "video/mp4")},
        data={"settings": settings},
    )

    assert response.status_code == 201
    project = response.json()
    source = Path(project["source_path"])
    assert source.name == "talk.mp4"
    assert source.parent.parent == (data_dir / "uploads").absolute()
    assert source.read_bytes() == b"video bytes"
    assert project["source_url"] is None
    assert project["settings"]["aspect"] == "1:1"
    with Session(api_engine) as session:
        job = session.exec(select(JobRow)).one()
    assert (job.project_id, job.status) == (project["id"], "queued")


def test_upload_without_settings_uses_the_defaults(client: TestClient) -> None:
    assert upload(client)["settings"]["num_clips"] == 10


def test_upload_keeps_only_the_last_part_of_the_file_name(
    client: TestClient, data_dir: Path
) -> None:
    project = upload(client, name="../../outside/evil.mp4")

    source = Path(project["source_path"])
    assert source.name == "evil.mp4"
    assert source.parent.parent == (data_dir / "uploads").absolute()


def test_upload_rejects_an_empty_file(client: TestClient, data_dir: Path) -> None:
    response = client.post(
        "/api/projects/upload", files={"file": ("a.mp4", b"", "video/mp4")}
    )

    assert "empty" in assert_error(response, 422, "validation_error")
    assert list((data_dir / "uploads").iterdir()) == []
    assert client.get("/api/projects").json() == []


@pytest.mark.parametrize("settings", ["not json", '{"num_clips": 99}'])
def test_upload_rejects_invalid_settings(client: TestClient, settings: str) -> None:
    response = client.post(
        "/api/projects/upload",
        files={"file": ("a.mp4", b"x", "video/mp4")},
        data={"settings": settings},
    )

    assert "settings" in assert_error(response, 422, "validation_error")
    assert client.get("/api/projects").json() == []


def test_upload_without_a_file_is_a_validation_error(client: TestClient) -> None:
    response = client.post("/api/projects/upload", data={"settings": "{}"})

    assert "file" in assert_error(response, 422, "validation_error")


def test_list_projects_is_newest_first(client: TestClient) -> None:
    assert client.get("/api/projects").json() == []
    first = client.post("/api/projects", json={"url": URL}).json()["id"]
    second = client.post("/api/projects", json={"url": URL + "2"}).json()["id"]

    response = client.get("/api/projects")

    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == [second, first]


def test_get_project(client: TestClient) -> None:
    created = client.post("/api/projects", json={"url": URL}).json()

    response = client.get(f"/api/projects/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_project_is_404(client: TestClient) -> None:
    message = assert_error(client.get("/api/projects/99"), 404, "not_found")
    assert "project 99" in message


def test_get_project_with_a_bad_id_is_422(client: TestClient) -> None:
    response = client.get("/api/projects/abc")

    assert "project_id" in assert_error(response, 422, "validation_error")


def test_delete_project_removes_its_rows_and_files(
    client: TestClient, api_engine: Engine
) -> None:
    uploaded = upload(client)
    project_id = uploaded["id"]
    with Session(api_engine) as session:
        job_id = session.exec(select(JobRow.id)).one()
    add_clip(api_engine, project_id, "rendered", 80)
    work = job_dir(job_id)
    work.mkdir(parents=True)
    (work / "source.mp4").write_bytes(b"x")
    output = project_output(project_id)
    output.mkdir(parents=True)
    (output / "1.mp4").write_bytes(b"x")
    other = client.post("/api/projects", json={"url": URL}).json()["id"]

    response = client.delete(f"/api/projects/{project_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert not work.exists()
    assert not output.exists()
    assert not Path(uploaded["source_path"]).parent.exists()
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    assert [p["id"] for p in client.get("/api/projects").json()] == [other]
    with Session(api_engine) as session:
        assert session.exec(select(ClipRow)).all() == []
        assert [j.project_id for j in session.exec(select(JobRow))] == [other]


def test_delete_project_keeps_a_source_that_was_not_uploaded(
    client: TestClient, api_engine: Engine, tmp_path: Path
) -> None:
    video = tmp_path / "mine" / "talk.mp4"
    video.parent.mkdir()
    video.write_bytes(b"x")
    project_id = add_project(api_engine)
    with Session(api_engine) as session:
        row = session.get(ProjectRow, project_id)
        assert row is not None
        row.source_path = str(video)
        session.commit()

    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert video.read_bytes() == b"x"


def test_delete_unknown_project_is_404(client: TestClient) -> None:
    assert_error(client.delete("/api/projects/99"), 404, "not_found")


def test_delete_project_with_a_running_job_is_a_conflict(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    add_job(api_engine, project_id, "running")

    assert_error(client.delete(f"/api/projects/{project_id}"), 409, "conflict")
    assert client.get(f"/api/projects/{project_id}").status_code == 200


def test_the_worker_runs_a_job_queued_by_an_upload(data_dir: Path) -> None:
    with TestClient(create_app()) as client:
        project = upload(client, name="junk.mp4", data=b"not a video")
        deadline = time.monotonic() + 60
        status = project["status"]
        while status not in ("done", "failed") and time.monotonic() < deadline:
            time.sleep(0.05)
            status = client.get(f"/api/projects/{project['id']}").json()["status"]

    assert status == "failed"
