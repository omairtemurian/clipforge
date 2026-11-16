"""Tests of POST /clips/{id}/post-copy: the post text of a clip on a
platform from a recorded LLM reply, the credit line of its project, and the
errors."""

import json
from pathlib import Path
from typing import Any

import pytest
from apihelpers import assert_error
from clipforge.api.app import create_app
from clipforge.db import ProjectRow
from clipforge.llm_http import LLMError
from fakes import FIXTURES, FakeLLMClient
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session

FIRST = json.loads((FIXTURES / "post_copy" / "replies.json").read_text())["first"]
NOW = {"title": "Old", "caption": "Old text.", "hashtags": ["old"]}


class Refusing:
    """An LLM that cannot be reached."""

    def complete_json(self, system: str, user: str) -> str:
        raise LLMError("refused")


def setup(client: TestClient, sample_mp4: Path, credit: str = "") -> int:
    """Add a clip with a transcript, in a project with credit; its id."""
    engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
    project_id = add_project(engine)
    add_work(engine, project_id, sample_mp4)
    with Session(engine) as session:
        project = session.get(ProjectRow, project_id)
        assert project is not None
        project.credit_line = credit
        session.commit()
    return add_clip(engine, project_id, "candidate", 80, "Pizza")


def post(client: TestClient, clip_id: int, **body: Any) -> Any:
    return client.post(f"/api/clips/{clip_id}/post-copy", json=body)


def test_post_copy_writes_the_platforms_text_and_saves_nothing(
    data_dir: Path, sample_mp4: Path
) -> None:
    llm = FakeLLMClient(json.dumps(FIRST))
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        clip_id = setup(client, sample_mp4, "Source: Standup Hour")

        response = post(client, clip_id, platform="tiktok")

        stored = client.get(f"/api/clips/{clip_id}").json()
    assert response.status_code == 200
    copy = response.json()
    assert copy["title"] == ""
    assert copy["caption"].startswith("Why yoga asked me one question\n\n")
    assert copy["caption"].endswith("\n\nSource: Standup Hour")
    assert copy["hashtags"] == ["yoga", "standup", "comedy", "FunnyMoments"]
    assert stored["title"] == "Pizza"
    assert "Platform: TikTok." in llm.calls[0][1]


def test_rewrite_options_are_passed_to_the_prompt(
    data_dir: Path, sample_mp4: Path
) -> None:
    llm = FakeLLMClient('{"title": "Short one", "description": "Two words."}')
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        clip_id = setup(client, sample_mp4)

        response = post(
            client,
            clip_id,
            platform="youtube",
            tone="funny",
            format="short",
            current=NOW,
        )

    assert response.json() == {
        "title": "Short one",
        "caption": "Two words.",
        "hashtags": ["old"],
    }
    user = llm.calls[0][1]
    assert "Tone: funny" in user and "Format: short" in user
    assert "Current description: Old text." in user


@pytest.mark.parametrize(
    "body",
    [
        {"platform": "x"},
        {"platform": "youtube", "tone": "rude", "current": NOW},
        {"platform": "youtube", "tone": "casual"},
        {"platform": "youtube", "hashtags": "lots", "current": NOW},
    ],
)
def test_bad_requests_are_422(client: TestClient, body: dict[str, Any]) -> None:
    assert_error(post(client, 1, **body), 422, "validation_error")


def test_llm_failures_are_502(data_dir: Path, sample_mp4: Path) -> None:
    invalid = FakeLLMClient("not json", repeat_last=True)
    for llm, message in ((invalid, "no valid"), (Refusing(), "refused")):
        with TestClient(create_app(run_worker=False, llm=llm)) as client:  # type: ignore[arg-type]
            clip_id = setup(client, sample_mp4)

            response = post(client, clip_id, platform="youtube")

        assert message in assert_error(response, 502, "llm_error")


def test_a_clip_without_a_transcript_or_a_clip_is_refused(
    data_dir: Path,
) -> None:
    with TestClient(create_app(run_worker=False, llm=FakeLLMClient())) as client:
        engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
        clip_id = add_clip(engine, add_project(engine), "candidate", 80)

        assert_error(post(client, 99, platform="youtube"), 404, "not_found")
        no_job = post(client, clip_id, platform="youtube")

    assert "no process job" in assert_error(no_job, 409, "conflict")
