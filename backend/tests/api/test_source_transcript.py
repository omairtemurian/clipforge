"""Tests of GET /projects/{id}/transcript, the source transcript that the
editor's add-section picker lists."""

from pathlib import Path

from apihelpers import assert_error
from fastapi.testclient import TestClient
from seed import add_project, add_work
from sqlalchemy import Engine


def test_the_source_transcript_answers_its_segments(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project = add_project(api_engine)
    add_work(api_engine, project, sample_mp4)

    response = client.get(f"/api/projects/{project}/transcript")

    assert response.status_code == 200
    body = response.json()
    assert len(body["segments"]) == 14
    assert body["segments"][0]["text"] == "Hi everyone."
    assert body["segments"][0]["start"] == 0.5


def test_the_source_transcript_needs_a_processed_project(
    client: TestClient, api_engine: Engine
) -> None:
    bare = add_project(api_engine)

    assert_error(client.get("/api/projects/999/transcript"), 404, "not_found")
    assert_error(client.get(f"/api/projects/{bare}/transcript"), 409, "conflict")
