"""Tests of reprompt (SPEC-v2 3.2): POST /api/projects/{id}/reprompt asks the
LLM again for the clips of a finished project, from its existing transcript,
and keeps the old clips as the previous result set."""

import json
from pathlib import Path
from typing import Any

import pytest
from apihelpers import assert_error
from clipforge import jobs, process
from clipforge.db import ClipRow, JobRow, ProjectRow
from clipforge.llm_http import LLMError
from clipforge.models import Clip, Job, Project, SignalList
from clipforge.pipeline import enrich
from clipforge.pipeline.step import SIGNALS, Step, StepSettings, write_json
from fakes import FakeLLMClient
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session, col, select

REQUEST = "every time he talks about his fridge"


class BrokenLLM:
    def complete_json(self, system: str, user: str) -> str:
        raise LLMError("the LLM is down")


def reply() -> str:
    clip = {
        "start": 1.5,
        "end": 32.9,
        "title": "The fridge that judges you",
        "hook_text": "My fridge reports me",
        "description": "His smart fridge has opinions.",
        "hashtags": ["comedy", "fridge", "smarthome"],
        "emphasis_words": ["fridge"],
        "reason": "He talks about his smart fridge, as asked.",
        "hook": 80,
        "flow": 75,
        "value": 70,
        "trend": 65,
    }
    return json.dumps({"clips": [clip]})


def record_steps(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the name of each step that process.run_step loads (the real
    steps still run)."""
    loaded: list[str] = []
    real_load_step = process.load_step

    def load_step(name: str) -> Step:
        loaded.append(name)
        return real_load_step(name)

    monkeypatch.setattr(process, "load_step", load_step)
    return loaded


@pytest.fixture
def done_project(api_engine: Engine, sample_mp4: Path) -> int:
    """A finished project: its work directory has the video, the transcript
    and the steps up to enrich; its one clip is the first result set."""
    project_id = add_project(api_engine)
    work = add_work(api_engine, project_id, sample_mp4)
    write_json(work / SIGNALS, SignalList([]))
    enrich.run(work, StepSettings(source="unused"), force=True)
    old = add_clip(api_engine, project_id, "rendered", 70, title="First result")
    with Session(api_engine) as session:
        project = session.get_one(ProjectRow, project_id)
        project.status = "done"
        output = Path(session.get_one(ClipRow, old).output_path or "")
        session.commit()
    output.parent.mkdir(parents=True)
    output.write_bytes(b"the first render")
    return project_id


def reprompt(client: TestClient, project_id: int, prompt: str = REQUEST) -> Any:
    return client.post(f"/api/projects/{project_id}/reprompt", json={"prompt": prompt})


def titles(client: TestClient, project_id: int, query: str = "") -> list[str]:
    clips = client.get(f"/api/projects/{project_id}/clips{query}").json()
    return [clip["title"] for clip in clips]


def test_reprompt_runs_curate_only_and_keeps_the_old_clips(
    client: TestClient,
    api_engine: Engine,
    done_project: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = record_steps(monkeypatch)
    llm = FakeLLMClient(reply())

    response = reprompt(client, done_project, f"  {REQUEST}\n")

    assert response.status_code == 202
    job = Job.model_validate(response.json())
    assert (job.kind, job.status, job.project_id) == ("reprompt", "queued", 1)
    assert client.get(f"/api/projects/{done_project}").json()["status"] == "queued"
    assert jobs.run_next(api_engine, llm=llm)

    assert loaded == ["visuals", "curate", "score", "snap"]
    [(system, _)] = llm.calls
    assert REQUEST in system
    project = Project.model_validate(client.get(f"/api/projects/{done_project}").json())
    assert (project.status, project.result_set) == ("done", 2)
    assert project.settings.keyword_prompt == REQUEST
    assert titles(client, done_project) == ["The fridge that judges you"]
    assert titles(client, done_project, "?result_set=1") == ["First result"]
    assert titles(client, done_project, "?result_set=3") == []
    with Session(api_engine) as session:
        rows = session.exec(select(ClipRow).order_by(col(ClipRow.id))).all()
        done = session.get_one(JobRow, job.id)
    old, new = (row.to_model() for row in rows)
    assert (old.result_set, old.status) == (1, "rendered")
    assert Path(old.output_path or "").read_bytes() == b"the first render"
    assert (new.result_set, new.status) == (2, "rendered")
    assert Path(new.output_path or "").stat().st_size > 1000
    assert (done.status, done.progress, done.error) == ("done", 1.0, None)


def test_a_second_reprompt_is_refused_while_the_first_one_waits(
    client: TestClient, done_project: int
) -> None:
    assert reprompt(client, done_project).status_code == 202

    message = assert_error(reprompt(client, done_project), 409, "conflict")

    assert "not finished" in message


@pytest.mark.parametrize("status", ["queued", "running", "failed"])
def test_a_project_that_is_not_done_cannot_be_reprompted(
    client: TestClient, api_engine: Engine, done_project: int, status: str
) -> None:
    with Session(api_engine) as session:
        session.get_one(ProjectRow, done_project).status = status  # type: ignore[assignment]
        session.commit()

    assert_error(reprompt(client, done_project), 409, "conflict")

    with Session(api_engine) as session:
        assert session.exec(select(JobRow).where(JobRow.kind == "reprompt")).all() == []


def test_a_project_without_a_transcript_cannot_be_reprompted(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    with Session(api_engine) as session:
        session.get_one(ProjectRow, project_id).status = "done"
        session.commit()

    assert_error(reprompt(client, project_id), 409, "conflict")


def test_reprompt_of_an_unknown_project_and_a_blank_prompt(
    client: TestClient, done_project: int
) -> None:
    assert_error(reprompt(client, 99), 404, "not_found")
    assert reprompt(client, done_project, "  \n ").status_code == 422
    assert reprompt(client, done_project, "").status_code == 422


def test_a_failed_reprompt_leaves_the_project_as_it_was(
    client: TestClient, api_engine: Engine, done_project: int
) -> None:
    job = Job.model_validate(reprompt(client, done_project).json())

    assert jobs.run_next(api_engine, llm=BrokenLLM())

    project = Project.model_validate(client.get(f"/api/projects/{done_project}").json())
    assert (project.status, project.result_set) == ("done", 1)
    assert titles(client, done_project) == ["First result"]
    failed = client.get(f"/api/jobs/{job.id}").json()
    assert failed["status"] == "failed"
    assert "the LLM is down" in failed["error"]
    # The project can be reprompted again.
    assert reprompt(client, done_project).status_code == 202


def test_clips_of_the_first_processing_are_in_set_one(
    client: TestClient, done_project: int
) -> None:
    clips = client.get(f"/api/projects/{done_project}/clips").json()

    assert [Clip.model_validate(clip).result_set for clip in clips] == [1]
