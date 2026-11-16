"""Tests of the resumable chunked upload endpoints (/api/uploads)."""

import hashlib
from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge import uploads
from clipforge.db import JobRow, ProjectRow
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

VIDEO = bytes(range(256)) * 40


def open_upload(
    client: TestClient, size: int = len(VIDEO), name: str = "talk.mp4"
) -> str:
    """Open a session for a file of size bytes and return its id."""
    response = client.post("/api/uploads", json={"filename": name, "size": size})
    assert response.status_code == 201
    body = response.json()
    assert body["offset"] == 0
    return str(body["id"])


def send(
    client: TestClient,
    upload_id: str,
    offset: int,
    chunk: bytes,
    sha: str | None = None,
):  # type: ignore[no-untyped-def]
    """PATCH one chunk at offset with its SHA-256 (or the given one)."""
    return client.patch(
        f"/api/uploads/{upload_id}",
        params={"offset": offset},
        content=chunk,
        headers={
            "X-Chunk-SHA256": sha or hashlib.sha256(chunk).hexdigest(),
            "Content-Type": "application/octet-stream",
        },
    )


def test_a_chunked_upload_becomes_a_queued_project(
    client: TestClient, api_engine: Engine, data_dir: Path
) -> None:
    upload_id = open_upload(client)
    for offset in range(0, len(VIDEO), 4000):
        response = send(client, upload_id, offset, VIDEO[offset : offset + 4000])
        assert response.status_code == 200
        assert response.json()["offset"] == min(offset + 4000, len(VIDEO))

    response = client.post(
        f"/api/uploads/{upload_id}/complete",
        json={"settings": {"num_clips": 2}, "source_rights": "own"},
    )

    assert response.status_code == 201
    project = response.json()
    assert project["status"] == "queued"
    assert project["settings"]["num_clips"] == 2
    assert project["source_rights"] == "own"
    with Session(api_engine) as session:
        row = session.exec(select(ProjectRow)).one()
        job = session.exec(select(JobRow)).one()
    assert row.source_path is not None
    saved = Path(row.source_path)
    assert saved.name == "talk.mp4"
    assert saved.read_bytes() == VIDEO
    assert saved.parent.parent == data_dir / "uploads"
    assert (job.kind, job.status) == ("process", "queued")
    assert list((data_dir / "upload_sessions").iterdir()) == []
    assert_error(client.get(f"/api/uploads/{upload_id}"), 404, "not_found")


def test_an_interrupted_upload_resumes_from_the_reported_offset(
    client: TestClient,
) -> None:
    upload_id = open_upload(client)
    assert send(client, upload_id, 0, VIDEO[:3000]).status_code == 200
    # The connection drops: the client re-sends the same chunk at offset 0.
    assert_error(send(client, upload_id, 0, VIDEO[:3000]), 409, "offset_mismatch")

    resumed_at = client.get(f"/api/uploads/{upload_id}").json()["offset"]
    assert resumed_at == 3000
    assert send(client, upload_id, resumed_at, VIDEO[resumed_at:]).status_code == 200

    response = client.post(f"/api/uploads/{upload_id}/complete", json={})
    assert response.status_code == 201
    assert Path(response.json()["source_path"]).read_bytes() == VIDEO


def test_a_chunk_whose_checksum_does_not_match_is_rejected(client: TestClient) -> None:
    upload_id = open_upload(client)

    response = send(
        client, upload_id, 0, VIDEO[:100], sha=hashlib.sha256(b"x").hexdigest()
    )

    assert_error(response, 422, "checksum_mismatch")
    assert client.get(f"/api/uploads/{upload_id}").json()["offset"] == 0


def test_a_chunk_past_the_declared_size_is_rejected(client: TestClient) -> None:
    upload_id = open_upload(client, size=10)

    assert_error(send(client, upload_id, 0, b"x" * 11), 422, "validation_error")


@pytest.mark.parametrize("size", [0, uploads.MAX_UPLOAD_BYTES + 1])
def test_the_declared_size_must_be_between_one_byte_and_30_gb(
    client: TestClient, size: int
) -> None:
    response = client.post("/api/uploads", json={"filename": "big.mp4", "size": size})

    assert_error(response, 422, "validation_error")


def test_a_30_gb_upload_is_accepted_when_the_disk_has_room(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(uploads, "free_bytes", lambda _path: 40 * 1024**3)

    response = client.post(
        "/api/uploads", json={"filename": "big.mp4", "size": uploads.MAX_UPLOAD_BYTES}
    )

    assert response.status_code == 201
    assert response.json()["size"] == uploads.MAX_UPLOAD_BYTES


def test_too_little_free_disk_space_is_507(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, data_dir: Path
) -> None:
    monkeypatch.setattr(uploads, "free_bytes", lambda _path: 2 * 1024**3)

    response = client.post(
        "/api/uploads", json={"filename": "big.mp4", "size": 3 * 1024**3}
    )

    message = assert_error(response, 507, "insufficient_storage")
    assert "free" in message
    assert list((data_dir / "upload_sessions").iterdir()) == []


def test_complete_before_every_byte_is_in_is_409(client: TestClient) -> None:
    upload_id = open_upload(client)
    send(client, upload_id, 0, VIDEO[:10])

    response = client.post(f"/api/uploads/{upload_id}/complete", json={})

    assert_error(response, 409, "upload_incomplete")
    assert client.get("/api/projects").json() == []


def test_cancel_drops_the_session(client: TestClient, data_dir: Path) -> None:
    upload_id = open_upload(client)
    send(client, upload_id, 0, VIDEO[:10])

    assert client.delete(f"/api/uploads/{upload_id}").status_code == 204

    assert_error(client.get(f"/api/uploads/{upload_id}"), 404, "not_found")
    assert list((data_dir / "upload_sessions").iterdir()) == []


@pytest.mark.parametrize("upload_id", ["..", "abc", "0" * 31 + "/"])
def test_an_unknown_or_malformed_id_is_404(client: TestClient, upload_id: str) -> None:
    response = client.get(f"/api/uploads/{upload_id}")

    assert response.status_code == 404


def test_the_file_name_keeps_only_its_last_component(client: TestClient) -> None:
    response = client.post(
        "/api/uploads", json={"filename": "..\\..\\evil/talk.mp4", "size": 5}
    )

    assert response.json()["filename"] == "talk.mp4"


def test_a_chunk_over_the_chunk_limit_is_413(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(uploads, "MAX_CHUNK_BYTES", 8)
    upload_id = open_upload(client)

    assert_error(send(client, upload_id, 0, VIDEO[:9]), 413, "chunk_too_large")
