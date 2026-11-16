"""Tests of GET /clips/{id}/transcript, the words the clip editor shows."""

from pathlib import Path

from apihelpers import assert_error
from clipforge.models import Word
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine


def texts(response_json: list[dict[str, object]]) -> list[str]:
    """Return the texts of a list of words."""
    return [Word.model_validate(item).text for item in response_json]


def test_transcript_has_the_clip_and_30_s_around_it(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)

    response = client.get(f"/api/clips/{clip_id}/transcript")

    assert response.status_code == 200
    words = response.json()
    # Clip 10-12.5 s: words starting from 0 s up to 42.5 s.
    assert texts(words)[:3] == ["Hi", "everyone.", "So,"]
    assert texts(words)[-3:] == ["me", "home.", "Uh,"]
    assert words[0] == {
        "text": "Hi",
        "start": 0.5,
        "end": 0.75,
        "speaker": "S0",
        "prob": words[0]["prob"],
        "approximate": False,
    }


def test_transcript_context_can_be_narrower(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)

    response = client.get(f"/api/clips/{clip_id}/transcript?context=2")

    assert response.status_code == 200
    assert " ".join(texts(response.json())) == (
        "I listened, and my body said, why are we on the floor?"
    )


def test_transcript_errors(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)

    assert_error(client.get("/api/clips/42/transcript"), 404, "not_found")
    no_job = client.get(f"/api/clips/{clip_id}/transcript")
    assert "no process job" in assert_error(no_job, 409, "conflict")
    work = add_work(api_engine, project_id, sample_mp4)
    (work / "transcript.json").unlink()
    missing = client.get(f"/api/clips/{clip_id}/transcript")
    assert "transcript.json" in assert_error(missing, 409, "conflict")
    too_wide = client.get(f"/api/clips/{clip_id}/transcript?context=301")
    assert_error(too_wide, 422, "validation_error")
