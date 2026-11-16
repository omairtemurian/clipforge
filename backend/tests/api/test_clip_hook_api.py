"""Tests of viral hooks through the API (SPEC-v2 3.5): the templates are
listed, a hook is applied with text from the clip's captions, an LLM line
about its theme (mocked) or given text, edited and removed, each a version
that undo takes back; errors answer 404, 409, 422 or 502, and the preview
key changes with the hook."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge.api.app import create_app
from clipforge.db import ClipRow
from clipforge.hooks_templates import load_templates
from clipforge.llm_http import LLMError
from clipforge.models import Clip, ClipHook, FaceBox
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.preview import preview_key
from fakes import FakeLLMClient
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


class FailingLLM:
    """An LLM that cannot be reached."""

    def complete_json(self, system: str, user: str) -> str:
        raise LLMError("POST https://llm.test/chat/completions failed: refused")


def stored(engine: Engine, clip_id: int) -> Clip:
    """Return clip clip_id as the database has it."""
    with Session(engine) as session:
        return session.get_one(ClipRow, clip_id).to_model()


@pytest.fixture
def llm() -> FakeLLMClient:
    """An LLM whose first hook reply is too long and second is valid."""
    return FakeLLMClient(
        json.dumps({"text": "x" * 61}), json.dumps({"text": ' "Why are we here?" '})
    )


@pytest.fixture
def llm_client(
    data_dir: Path, llm: FakeLLMClient
) -> Iterator[tuple[TestClient, Engine]]:
    """A client of an app that asks llm, and its engine."""
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        yield client, client.app.state.engine  # type: ignore[attr-defined]


def test_the_templates_are_listed(client: TestClient) -> None:
    response = client.get("/api/hook-templates")

    assert response.status_code == 200
    templates = response.json()
    assert [t["name"] for t in templates] == sorted(load_templates())
    assert len(templates) >= 5
    assert all(2.0 <= t["duration"] <= 3.0 and t["sound"] for t in templates)
    assert all(t["label"] and t["description"] for t in templates)


def test_a_hook_from_the_captions_is_saved_as_a_version(
    llm_client: tuple[TestClient, Engine], sample_mp4: Path
) -> None:
    client, engine = llm_client
    project_id = add_project(engine)
    add_work(engine, project_id, sample_mp4)
    clip_id = add_clip(engine, project_id, "candidate", 80, "Pizza")
    assert client.get(f"/api/clips/{clip_id}").json()["hook"] is None

    response = client.post(f"/api/clips/{clip_id}/hook", json={"template": "slam_pop"})

    assert response.status_code == 200
    hook = ClipHook(template="slam_pop", text="said, why are we on", duration=2.5)
    assert Clip.model_validate(response.json()) == stored(engine, clip_id)
    assert stored(engine, clip_id).hook == hook
    history = client.get(f"/api/clips/{clip_id}/versions").json()
    assert history["versions"][-1]["fields"] == ["hook"]
    assert client.post(f"/api/clips/{clip_id}/undo").json()["hook"] is None


def test_a_hook_from_the_theme_asks_the_llm_again_until_valid(
    llm_client: tuple[TestClient, Engine], llm: FakeLLMClient, sample_mp4: Path
) -> None:
    client, engine = llm_client
    project_id = add_project(engine)
    add_work(engine, project_id, sample_mp4)
    clip_id = add_clip(engine, project_id, "candidate", 80, "Pizza")

    response = client.post(
        f"/api/clips/{clip_id}/hook",
        json={"template": "slow_push", "source": "theme", "duration": 2.0},
    )

    assert response.status_code == 200
    assert response.json()["hook"] == {
        "template": "slow_push",
        "text": "Why are we here?",
        "duration": 2.0,
    }
    (system, first), (_, retry) = llm.calls
    assert "maxLength" in system and "hook" in system
    assert "What is said in the clip:\nsaid, why are we on\n\nTitle: Pizza" in first
    assert "at most 60 characters" in retry


def test_given_text_needs_no_transcript_and_can_be_edited_and_removed(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    url = f"/api/clips/{clip_id}/hook"

    applied = client.post(
        url, json={"template": "neon_rise", "source": "text", "text": " Wait  for it "}
    )
    edited = client.patch(url, json={"template": "boxed_drop", "duration": 3.0})
    removed = client.delete(url)

    assert applied.json()["hook"] == {
        "template": "neon_rise",
        "text": "Wait  for it",
        "duration": 2.5,
    }
    assert edited.json()["hook"] == {
        "template": "boxed_drop",
        "text": "Wait  for it",
        "duration": 3.0,
    }
    assert removed.status_code == 200 and removed.json()["hook"] is None
    assert stored(api_engine, clip_id).hook is None
    assert client.delete(url).json()["hook"] is None
    history = client.get(f"/api/clips/{clip_id}/versions").json()
    assert [v["fields"] for v in history["versions"][-3:]] == [["hook"]] * 3
    assert client.post(f"/api/clips/{clip_id}/undo").json()["hook"]["duration"] == 3.0


@pytest.mark.parametrize(
    "body",
    [
        {"template": "slam_pop", "source": "text"},
        {"template": "slam_pop", "source": "captions", "text": "hi"},
        {"template": "slam_pop", "source": "text", "text": "x" * 61},
        {"template": "slam_pop", "source": "text", "text": "   "},
        {"template": "slam_pop", "source": "text", "text": "hi", "duration": 1.5},
        {"template": "slam_pop", "source": "vibes"},
        {"template": "nope", "source": "text", "text": "hi"},
    ],
)
def test_invalid_hooks_are_refused(
    client: TestClient, api_engine: Engine, body: dict[str, object]
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)

    response = client.post(f"/api/clips/{clip_id}/hook", json=body)

    assert_error(response, 422, "validation_error")
    assert stored(api_engine, clip_id).hook is None


def test_hook_errors(client: TestClient, api_engine: Engine) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    rendering = add_clip(api_engine, project_id, "rendering", 80)
    text = {"template": "slam_pop", "source": "text", "text": "hi"}

    assert_error(client.post("/api/clips/999/hook", json=text), 404, "not_found")
    assert_error(client.delete("/api/clips/999/hook"), 404, "not_found")
    assert "no hook" in assert_error(
        client.patch(f"/api/clips/{clip_id}/hook", json={"text": "yo"}),
        404,
        "not_found",
    )
    assert "rendering" in assert_error(
        client.post(f"/api/clips/{rendering}/hook", json=text), 409, "conflict"
    )
    no_transcript = client.post(
        f"/api/clips/{clip_id}/hook", json={"template": "slam_pop"}
    )
    assert_error(no_transcript, 409, "conflict")
    client.post(f"/api/clips/{clip_id}/hook", json=text)
    assert_error(
        client.patch(f"/api/clips/{clip_id}/hook", json={"template": "nope"}),
        422,
        "validation_error",
    )


@pytest.mark.parametrize("llm", [FakeLLMClient("not json", repeat_last=True)])
def test_theme_failures_are_502(
    llm_client: tuple[TestClient, Engine], sample_mp4: Path
) -> None:
    client, engine = llm_client
    project_id = add_project(engine)
    add_work(engine, project_id, sample_mp4)
    clip_id = add_clip(engine, project_id, "candidate", 80)
    body = {"template": "slam_pop", "source": "theme"}

    response = client.post(f"/api/clips/{clip_id}/hook", json=body)

    assert "no valid hook line" in assert_error(response, 502, "llm_error")
    assert stored(engine, clip_id).hook is None


def test_an_unreachable_llm_is_502(data_dir: Path, sample_mp4: Path) -> None:
    with TestClient(create_app(run_worker=False, llm=FailingLLM())) as client:
        engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
        project_id = add_project(engine)
        add_work(engine, project_id, sample_mp4)
        clip_id = add_clip(engine, project_id, "candidate", 80)
        body = {"template": "slam_pop", "source": "theme"}

        response = client.post(f"/api/clips/{clip_id}/hook", json=body)

    assert "refused" in assert_error(response, 502, "llm_error")


def test_the_preview_key_changes_with_the_hook(api_engine: Engine) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    clip = stored(api_engine, clip_id)
    faces: list[list[FaceBox]] = [[] for _ in sample_times(10.0, 12.5)]
    plan = plan_crop(ClipSpan(clip_id, 10.0, 12.5), "9:16", (1280, 720), faces, [])
    hooked = clip.model_copy(update={"hook": ClipHook(template="slam_pop", text="hi")})

    assert preview_key(hooked, plan) != preview_key(clip, plan)
