"""Tests of speech cleanup through the API (SPEC-v2 3.5): the filler
languages, a preview of the saved clip (fillers, pause threshold, bad
takes from a mocked LLM) that leaves it unchanged, and apply with unchecked
items, a version that undo takes back; errors answer 404, 409, 422 or
502."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from apihelpers import assert_error
from builders import FIXTURE_LAUGHS
from clipforge.api.app import create_app
from clipforge.llm_http import LLMError
from clipforge.models import SignalList
from clipforge.pipeline.step import SIGNALS, write_json
from fakes import FakeLLMClient
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine

UM = {"start": 6.2, "end": 7.55, "kind": "filler", "text": "um"}
LIKE = {"start": 22.6, "end": 24.15, "kind": "filler", "text": "like"}
# Words 27-32 of clip 0.5-34.35: "Then I bought one of those".
RETAKE = {
    "start": 16.9,
    "end": 18.84,
    "kind": "bad_take",
    "text": "Then I bought one of those",
}


class FailingLLM:
    """An LLM that cannot be reached."""

    def complete_json(self, system: str, user: str) -> str:
        raise LLMError("POST https://llm.test/chat/completions failed: refused")


def seed_clip(engine: Engine, sample_mp4: Path, status: str = "candidate") -> int:
    """Add a project processed from the fixture (with its laughs) and its
    clip 0.5-34.35 s with status; return the clip's id."""
    project_id = add_project(engine)
    work = add_work(engine, project_id, sample_mp4)
    write_json(work / SIGNALS, SignalList(list(FIXTURE_LAUGHS)))
    return add_clip(engine, project_id, status, 80, start=0.5, end=34.35)


@pytest.fixture
def llm() -> FakeLLMClient:
    """An LLM that finds the bad take of words 27-32."""
    return FakeLLMClient(json.dumps({"takes": [{"first": 27, "last": 32}]}))


@pytest.fixture
def llm_client(
    data_dir: Path, llm: FakeLLMClient
) -> Iterator[tuple[TestClient, Engine]]:
    """A client of an app that asks llm, and its engine."""
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        yield client, client.app.state.engine  # type: ignore[attr-defined]


def test_filler_languages_are_listed(client: TestClient) -> None:
    response = client.get("/api/filler-languages")

    assert response.status_code == 200
    assert {"en", "es", "fa", "de"} <= set(response.json())
    assert response.json() == sorted(response.json())


def test_a_preview_lists_fillers_and_pauses_and_leaves_the_clip(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    clip_id = seed_clip(api_engine, sample_mp4)
    url = f"/api/clips/{clip_id}/cleanup/preview"

    default = client.post(url, json={})
    longer = client.post(url, json={"pause_threshold_s": 2.0, "fillers": False})

    assert default.status_code == 200
    assert default.json() == {"filler_language": "en", "items": [UM, LIKE]}
    assert longer.json()["items"] == []
    no_laughs = client.post(url, json={"language": "es", "pause_threshold_s": 1})
    assert no_laughs.json()["filler_language"] == "es"
    assert client.get(f"/api/clips/{clip_id}").json()["cut_ranges"] == []


def test_the_llm_finds_bad_takes_for_the_preview(
    llm_client: tuple[TestClient, Engine], llm: FakeLLMClient, sample_mp4: Path
) -> None:
    client, engine = llm_client
    clip_id = seed_clip(engine, sample_mp4)

    response = client.post(
        f"/api/clips/{clip_id}/cleanup/preview",
        json={"bad_takes": True, "pauses": False},
    )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {"start": 6.75, "end": 7.15, "kind": "filler", "text": "um"},
        RETAKE,
        {"start": 23.25, "end": 23.6, "kind": "filler", "text": "like"},
    ]
    [(system, user)] = llm.calls
    assert "bad takes" in system
    assert "27: Then\n28: I\n" in user


def test_apply_cuts_the_checked_items_and_undo_takes_them_back(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    clip_id = seed_clip(api_engine, sample_mp4)
    items = [UM, RETAKE, LIKE]

    response = client.post(
        f"/api/clips/{clip_id}/cleanup/apply", json={"items": items, "unchecked": [1]}
    )

    assert response.status_code == 200
    assert response.json()["cut_ranges"] == [[6.2, 7.55], [22.6, 24.15]]
    assert client.get(f"/api/clips/{clip_id}").json()["cut_ranges"] == [
        [6.2, 7.55],
        [22.6, 24.15],
    ]
    history = client.get(f"/api/clips/{clip_id}/versions").json()
    assert history["versions"][-1]["fields"] == ["cut_ranges"]
    preview = client.post(f"/api/clips/{clip_id}/cleanup/preview", json={})
    assert preview.json()["items"] == []
    undone = client.post(f"/api/clips/{clip_id}/undo").json()
    assert undone["cut_ranges"] == []


def test_preview_errors(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    clip_id = seed_clip(api_engine, sample_mp4)
    url = f"/api/clips/{clip_id}/cleanup/preview"
    no_work = add_clip(api_engine, add_project(api_engine), "candidate", 80)

    assert_error(
        client.post("/api/clips/42/cleanup/preview", json={}), 404, "not_found"
    )
    assert_error(
        client.post(f"/api/clips/{no_work}/cleanup/preview", json={}), 409, "conflict"
    )
    for body in ({"pause_threshold_s": 0.1}, {"fillers": "x"}, {"other": 1}):
        assert_error(client.post(url, json=body), 422, "validation_error")


@pytest.mark.parametrize("llm", [FailingLLM(), FakeLLMClient("{}", repeat_last=True)])
def test_bad_takes_answer_502_when_the_llm_fails(
    llm_client: tuple[TestClient, Engine], sample_mp4: Path
) -> None:
    client, engine = llm_client
    clip_id = seed_clip(engine, sample_mp4)

    response = client.post(
        f"/api/clips/{clip_id}/cleanup/preview", json={"bad_takes": True}
    )

    assert_error(response, 502, "llm_error")


def test_apply_errors(client: TestClient, api_engine: Engine, sample_mp4: Path) -> None:
    clip_id = seed_clip(api_engine, sample_mp4)
    rendering = seed_clip(api_engine, sample_mp4, "rendering")
    url = f"/api/clips/{clip_id}/cleanup/apply"
    everything = {"start": 0.5, "end": 34.35, "kind": "pause", "text": ""}

    assert_error(
        client.post("/api/clips/42/cleanup/apply", json={"items": []}), 404, "not_found"
    )
    assert_error(
        client.post(f"/api/clips/{rendering}/cleanup/apply", json={"items": [UM]}),
        409,
        "conflict",
    )
    for body in (
        {"items": [UM], "unchecked": [1]},
        {"items": [UM | {"end": 6.0}]},
        {"items": [everything]},
    ):
        assert_error(client.post(url, json=body), 422, "validation_error")
    assert client.get(f"/api/clips/{clip_id}").json()["cut_ranges"] == []
