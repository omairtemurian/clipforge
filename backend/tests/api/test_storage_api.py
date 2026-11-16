"""Storage manager endpoints: GET /storage (disk use per project), POST
/projects/{id}/cleanup (only the files a project can do without) and POST
/projects/{id}/archive (keeps the output, transcript and thumbnail; the clips
can no longer be rendered)."""

from pathlib import Path

from apihelpers import assert_error
from clipforge.db import ProjectRow
from clipforge.models import JobStatus, StorageCleanup, StorageReport
from clipforge.pipeline.face_cache import FACE_CACHE
from clipforge.pipeline.render import clip_output
from clipforge.pipeline.step import AUDIO, META, SOURCE, THUMB, TRANSCRIPT
from clipforge.preview import previews_dir
from clipforge.uploads import uploads_dir
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


def set_project(engine: Engine, project_id: int, **fields: object) -> None:
    with Session(engine) as session:
        row = session.get_one(ProjectRow, project_id)
        for name, value in fields.items():
            setattr(row, name, value)
        session.add(row)
        session.commit()


def project_with_files(
    engine: Engine, sample_mp4: Path, status: JobStatus = "done"
) -> tuple[int, Path, Path, int]:
    """Add an uploaded project with its work files, a rendered clip and a
    preview; return its id, work dir, upload dir and the clip id."""
    project_id = add_project(engine)
    upload = uploads_dir().absolute() / "abc123"
    upload.mkdir(parents=True)
    (upload / "talk.mp4").write_bytes(b"u" * 1000)
    set_project(engine, project_id, status=status, source_path=str(upload / "talk.mp4"))
    work = add_work(engine, project_id, sample_mp4)
    (work / AUDIO).write_bytes(b"a" * 500)
    (work / FACE_CACHE).write_bytes(b"f" * 200)
    (work / THUMB).write_bytes(b"t" * 10)
    clip_id = add_clip(engine, project_id, "rendered", 80, "Best bit")
    video = clip_output(project_id, clip_id)
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"v" * 300)
    previews_dir(project_id).mkdir(parents=True)
    (previews_dir(project_id) / "7-key.mp4").write_bytes(b"p" * 50)
    return project_id, work, upload, clip_id


def test_storage_lists_each_project_with_its_bytes(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id, work, _, _ = project_with_files(api_engine, sample_mp4)
    empty = add_project(api_engine)

    response = client.get("/api/storage")

    assert response.status_code == 200
    report = StorageReport.model_validate(response.json())
    assert [item.project_id for item in report.projects] == [project_id, empty]
    usage = report.projects[0]
    work_bytes = sum(f.stat().st_size for f in work.rglob("*") if f.is_file())
    assert (usage.source_bytes, usage.work_bytes, usage.output_bytes) == (
        1000,
        work_bytes,
        350,
    )
    assert usage.cleanable_bytes == 1000 + 500 + 200 + 50
    assert usage.total_bytes == 1000 + work_bytes + 350
    assert response.json()["projects"][0]["total_bytes"] == usage.total_bytes
    assert report.projects[1].total_bytes == 0
    assert report.total_bytes == usage.total_bytes
    assert report.free_bytes > 0
    assert report.data_dir.endswith("data")


def test_cleanup_deletes_only_the_files_the_project_can_do_without(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id, work, upload, clip_id = project_with_files(api_engine, sample_mp4)

    response = client.post(f"/api/projects/{project_id}/cleanup")

    assert response.status_code == 200
    result = StorageCleanup.model_validate(response.json())
    assert result.freed_bytes == 1000 + 500 + 200 + 50
    assert result.storage.cleanable_bytes == 0
    assert not (work / AUDIO).exists()
    assert not (work / FACE_CACHE).exists()
    assert not upload.exists()
    assert not previews_dir(project_id).exists()
    for kept in (SOURCE, TRANSCRIPT, META, THUMB):
        assert (work / kept).is_file()
    assert clip_output(project_id, clip_id).is_file()
    assert client.get(f"/api/projects/{project_id}").json()["archived_at"] is None
    again = client.post(f"/api/projects/{project_id}/cleanup")
    assert again.json()["freed_bytes"] == 0


def test_cleanup_of_a_failed_project_keeps_its_upload(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id, work, upload, _ = project_with_files(
        api_engine, sample_mp4, status="failed"
    )

    response = client.post(f"/api/projects/{project_id}/cleanup")

    assert response.status_code == 200
    assert (upload / "talk.mp4").is_file()
    assert not (work / AUDIO).exists()


def test_archive_keeps_the_output_transcript_and_thumbnail(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id, work, upload, clip_id = project_with_files(api_engine, sample_mp4)
    (work / "steps").mkdir()
    (work / "steps" / "ingest").write_text("")

    response = client.post(f"/api/projects/{project_id}/archive")

    assert response.status_code == 200
    result = StorageCleanup.model_validate(response.json())
    assert result.storage.archived_at is not None
    assert sorted(path.name for path in work.iterdir()) == sorted(
        [META, THUMB, TRANSCRIPT]
    )
    assert not upload.exists()
    assert clip_output(project_id, clip_id).is_file()
    assert result.storage.output_bytes == 300
    assert result.freed_bytes > 1000 + sample_mp4.stat().st_size
    assert client.get(f"/api/projects/{project_id}").json()["archived_at"]
    assert client.get(f"/api/media/{project_id}/thumbnail").status_code == 200


def test_an_archived_project_cannot_render_reprompt_or_make_clips(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id, _, _, clip_id = project_with_files(api_engine, sample_mp4)
    client.post(f"/api/projects/{project_id}/archive")

    assert_error(client.post(f"/api/clips/{clip_id}/render"), 409, "conflict")
    assert_error(
        client.post(f"/api/projects/{project_id}/reprompt", json={"prompt": "jokes"}),
        409,
        "conflict",
    )
    moment = {"project_id": project_id, "at": 1.0}
    assert_error(client.post("/api/search/clips", json=moment), 409, "conflict")


def test_cleanup_and_archive_wait_for_a_running_project(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id, work, _, _ = project_with_files(
        api_engine, sample_mp4, status="running"
    )

    for action in ("cleanup", "archive"):
        response = client.post(f"/api/projects/{project_id}/{action}")
        assert_error(response, 409, "conflict")
    assert (work / AUDIO).is_file()


def test_cleanup_and_archive_of_a_missing_project_are_404(client: TestClient) -> None:
    for action in ("cleanup", "archive"):
        assert_error(client.post(f"/api/projects/99/{action}"), 404, "not_found")
