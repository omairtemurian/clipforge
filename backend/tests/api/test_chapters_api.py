"""Tests of the topic chapter endpoints (SPEC-v2 3.2): chapters of a project
from the (fake) LLM, and clip by topic, which curates only the chosen
chapters and makes the clips the project's next result set."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from apihelpers import assert_error
from clipforge import jobs
from clipforge.api.app import create_app
from clipforge.db import ProjectRow
from clipforge.llm_http import LLMError
from clipforge.models import Chapter, Job, SignalList
from clipforge.pipeline import enrich
from clipforge.pipeline.step import SIGNALS, StepSettings, write_json
from fakes import FakeLLMClient
from fastapi.testclient import TestClient
from seed import add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session

CHAPTERS = json.dumps(
    {
        "chapters": [
            {"start": 0.5, "end": 16.9, "title": "Yoga", "summary": "Yoga."},
            {"start": 16.9, "end": 35.8, "title": "The fridge", "summary": "A fridge."},
            {"start": 35.8, "end": 59.5, "title": "The car", "summary": "A car."},
        ]
    }
)
FRIDGE_AND_CAR = (16.9, 59.5)


class BrokenLLM:
    def complete_json(self, system: str, user: str) -> str:
        raise LLMError("the LLM is down")


def clip_reply(start: float, end: float, title: str) -> str:
    clip = {
        "start": start,
        "end": end,
        "title": title,
        "hook_text": "A hook",
        "description": "About a topic.",
        "hashtags": ["comedy", "topic", "talk"],
        "emphasis_words": ["fridge"],
        "reason": "It is a complete moment.",
        "hook": 80,
        "flow": 75,
        "value": 70,
        "trend": 65,
    }
    return json.dumps({"clips": [clip]})


@pytest.fixture
def llm() -> FakeLLMClient:
    return FakeLLMClient(CHAPTERS)


@pytest.fixture
def chapter_client(data_dir: Path, llm: FakeLLMClient) -> Iterator[TestClient]:
    app = create_app(run_worker=False, caption_previews=False, llm=llm)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def engine(chapter_client: TestClient) -> Engine:
    engine: Engine = chapter_client.app.state.engine  # type: ignore[attr-defined]
    return engine


@pytest.fixture
def project(engine: Engine, sample_mp4: Path) -> int:
    """A finished project whose work directory has the enriched transcript."""
    project_id = add_project(engine)
    work = add_work(engine, project_id, sample_mp4)
    write_json(work / SIGNALS, SignalList([]))
    enrich.run(work, StepSettings(source="unused"), force=True)
    with Session(engine) as session:
        session.get_one(ProjectRow, project_id).status = "done"
        session.commit()
    return project_id


def spans(chapters: list[dict[str, Any]]) -> list[tuple[int, float, float]]:
    return [(c["id"], c["start"], c["end"]) for c in chapters]


def test_chapters_are_made_by_the_llm_and_kept(
    chapter_client: TestClient, project: int
) -> None:
    url = f"/api/projects/{project}/chapters"
    assert chapter_client.get(url).json() == []

    response = chapter_client.post(url)

    assert response.status_code == 200
    [Chapter.model_validate(c) for c in response.json()]
    assert spans(response.json()) == [(1, 0.5, 16.9), (2, 16.9, 35.8), (3, 35.8, 59.5)]
    assert chapter_client.get(url).json() == response.json()


def test_chapters_of_a_project_without_a_transcript_or_that_is_unknown(
    chapter_client: TestClient, engine: Engine
) -> None:
    bare = add_project(engine)

    assert_error(chapter_client.post(f"/api/projects/{bare}/chapters"), 409, "conflict")
    assert_error(chapter_client.get(f"/api/projects/{bare}/chapters"), 409, "conflict")
    assert_error(chapter_client.post("/api/projects/99/chapters"), 404, "not_found")
    assert_error(chapter_client.get("/api/projects/99/chapters"), 404, "not_found")


def test_chapters_answer_502_when_the_llm_fails(
    chapter_client: TestClient, project: int
) -> None:
    chapter_client.app.state.llm = BrokenLLM()  # type: ignore[attr-defined]
    url = f"/api/projects/{project}/chapters"

    message = assert_error(chapter_client.post(url), 502, "llm_error")

    assert "the LLM is down" in message
    assert chapter_client.get(url).json() == []


def test_clip_by_topic_curates_only_the_chosen_chapters(
    chapter_client: TestClient, engine: Engine, project: int, llm: FakeLLMClient
) -> None:
    chapter_client.post(f"/api/projects/{project}/chapters")
    topic_llm = FakeLLMClient(clip_reply(16.85, 41.2, "The fridge and the car"))

    response = chapter_client.post(
        f"/api/projects/{project}/clip-by-topic", json={"chapters": [3, 2, 2]}
    )

    assert response.status_code == 202
    job = Job.model_validate(response.json())
    assert (job.kind, job.status) == ("reprompt", "queued")
    assert jobs.run_next(engine, llm=topic_llm)
    [(system, user)] = topic_llm.calls
    assert "[00:16.9-00:19.7]" in user and "My car has a voice assistant" in user
    assert "yoga" not in user and "Hi everyone." not in user
    assert "The user is looking for" not in system
    done = chapter_client.get(f"/api/projects/{project}").json()
    assert (done["status"], done["result_set"]) == ("done", 2)
    clips = chapter_client.get(f"/api/projects/{project}/clips").json()
    assert [c["title"] for c in clips] == ["The fridge and the car"]
    assert FRIDGE_AND_CAR[0] <= clips[0]["start"] < clips[0]["end"] <= FRIDGE_AND_CAR[1]


def test_clip_by_topic_drops_clips_outside_the_chapters_and_takes_a_prompt(
    chapter_client: TestClient, engine: Engine, project: int
) -> None:
    chapter_client.post(f"/api/projects/{project}/chapters")
    topic_llm = FakeLLMClient(clip_reply(1.5, 24.0, "A yoga clip"))

    body = {"chapters": [2, 3], "prompt": " the  smart fridge "}
    assert (
        chapter_client.post(
            f"/api/projects/{project}/clip-by-topic", json=body
        ).status_code
        == 202
    )
    assert jobs.run_next(engine, llm=topic_llm)

    [(system, _)] = topic_llm.calls
    assert "The user is looking for: the smart fridge\n" in system
    assert chapter_client.get(f"/api/projects/{project}/clips").json() == []
    settings = chapter_client.get(f"/api/projects/{project}").json()["settings"]
    assert settings["keyword_prompt"] == "the smart fridge"


def test_clip_by_topic_needs_chapters_that_exist(
    chapter_client: TestClient, project: int
) -> None:
    url = f"/api/projects/{project}/clip-by-topic"
    assert_error(chapter_client.post(url, json={"chapters": [1]}), 409, "conflict")

    chapter_client.post(f"/api/projects/{project}/chapters")

    message = assert_error(
        chapter_client.post(url, json={"chapters": [1, 4]}), 422, "validation_error"
    )
    assert "no chapter 4" in message
    assert chapter_client.post(url, json={"chapters": []}).status_code == 422
    assert chapter_client.post(url, json={}).status_code == 422
    assert_error(
        chapter_client.post("/api/projects/99/clip-by-topic", json={"chapters": [1]}),
        404,
        "not_found",
    )


def test_clip_by_topic_is_refused_while_the_project_is_not_done(
    chapter_client: TestClient, engine: Engine, project: int
) -> None:
    chapter_client.post(f"/api/projects/{project}/chapters")
    url = f"/api/projects/{project}/clip-by-topic"
    assert chapter_client.post(url, json={"chapters": [1]}).status_code == 202

    assert_error(chapter_client.post(url, json={"chapters": [1]}), 409, "conflict")
