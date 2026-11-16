"""Tests of auto sound effects through the API (SPEC-v2 3.5, api/sfx): the
bundled pack is in the asset library with its license, attribution and tags,
can be filtered and played, and the AI pass (a mocked LLM) puts its sounds
on a clip's sfx track, replacing its own earlier items and keeping the
owner's; errors answer 404, 409, 422 or 502."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge.api.app import create_app
from clipforge.llm_http import LLMError
from clipforge.pipeline.sfx import BUNDLED_SFX, SFX_DIR
from fakes import FakeLLMClient
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine

# Moments of clip 0.5-34.35 s: 26 is "floor?" at 12.49 s, 34 "fridges." at 18.74 s.
REPLY = json.dumps(
    {
        "sounds": [
            {"moment": 34, "tags": ["pop", "emphasis"]},
            {"moment": 26, "tags": ["punchline", "laugh"]},
        ]
    }
)


class FailingLLM:
    """An LLM that cannot be reached."""

    def complete_json(self, system: str, user: str) -> str:
        raise LLMError("POST https://llm.test/chat/completions failed: refused")


def seed_clip(engine: Engine, sample_mp4: Path, status: str = "candidate") -> int:
    """Add a project processed from the fixture and its clip 0.5-34.35 s
    with status; return the clip's id."""
    project_id = add_project(engine)
    add_work(engine, project_id, sample_mp4)
    return add_clip(engine, project_id, status, 80, start=0.5, end=34.35)


@pytest.fixture
def llm() -> FakeLLMClient:
    """An LLM that puts a pop on "fridges." and a laugh on "floor?"."""
    return FakeLLMClient(REPLY, repeat_last=True)


@pytest.fixture
def llm_client(
    data_dir: Path, llm: FakeLLMClient
) -> Iterator[tuple[TestClient, Engine]]:
    """A client of an app that asks llm, and its engine."""
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        yield client, client.app.state.engine  # type: ignore[attr-defined]


def test_the_pack_is_listed_with_license_attribution_and_tags(
    client: TestClient,
) -> None:
    sounds = client.get("/api/sfx").json()

    assert [sound["title"] for sound in sounds] == [s.title for s in BUNDLED_SFX]
    for sound, bundled in zip(sounds, BUNDLED_SFX, strict=True):
        asset = sound["asset"]
        assert sound["tags"] == list(bundled.tags)
        assert sound["duration"] == bundled.seconds
        assert asset["kind"] == "sfx"
        assert asset["license"] == "CC0-1.0"
        assert asset["attribution"] == bundled.attribution
        assert asset["tags"] == ["bundled", *bundled.tags]
        assert Path(asset["path"]) == SFX_DIR / bundled.file


def test_the_pack_is_filtered_by_tag_and_a_sound_is_played(
    client: TestClient,
) -> None:
    laughs = client.get("/api/sfx", params={"tag": " Punchline "}).json()
    first = laughs[0]["asset"]["id"]
    played = client.get(f"/api/sfx/{first}/file")

    assert [s["title"] for s in laughs] == ["Rimshot", "Crowd Laugh"]
    assert client.get("/api/sfx", params={"tag": "nope"}).json() == []
    assert played.status_code == 200
    assert played.headers["content-type"] == "audio/flac"
    assert played.content == (SFX_DIR / "rimshot_badum.flac").read_bytes()
    assert_error(client.get("/api/sfx/9999/file"), 404, "not_found")
    music = client.get("/api/music").json()[0]["asset"]["id"]
    assert_error(client.get(f"/api/sfx/{music}/file"), 404, "not_found")


def test_the_pack_is_in_the_asset_library_once(client: TestClient) -> None:
    again = TestClient(client.app)
    with again:
        sounds = again.get("/api/sfx").json()

    assert len(sounds) == len(BUNDLED_SFX)


def test_auto_sfx_puts_the_sounds_on_the_sfx_track(
    llm_client: tuple[TestClient, Engine], llm: FakeLLMClient, sample_mp4: Path
) -> None:
    client, engine = llm_client
    clip_id = seed_clip(engine, sample_mp4)
    pack = {sound["title"]: sound for sound in client.get("/api/sfx").json()}

    response = client.post(f"/api/clips/{clip_id}/auto-sfx", json={})

    assert response.status_code == 200
    items = response.json()["tracks"]["sfx"]
    assert [(i["id"], i["kind"], i["start"]) for i in items] == [
        ("auto-sfx-1", "audio", 12.49),
        ("auto-sfx-2", "audio", 18.74),
    ]
    assert [i["asset_id"] for i in items] == [
        pack["Crowd Laugh"]["asset"]["id"],
        pack["Bubble Pop"]["asset"]["id"],
    ]
    assert items[0]["props"] == {"volume": 0.6, "offset": 0.0}
    assert client.get(f"/api/clips/{clip_id}").json()["tracks"]["sfx"] == items
    [(system, user)] = llm.calls
    assert "sound effects" in system
    assert "26: 12.49s floor?" in user and "34: 18.74s fridges." in user


def test_a_second_run_replaces_its_items_and_keeps_the_owners(
    llm_client: tuple[TestClient, Engine], sample_mp4: Path
) -> None:
    client, engine = llm_client
    clip_id = seed_clip(engine, sample_mp4)
    pop = client.get("/api/sfx", params={"tag": "pop"}).json()[0]["asset"]["id"]
    own = {"id": "mine", "kind": "audio", "asset_id": pop, "start": 1.0, "end": 1.2}
    client.patch(f"/api/clips/{clip_id}/tracks", json={"sfx": [own]})

    first = client.post(f"/api/clips/{clip_id}/auto-sfx", json={})
    again = client.post(f"/api/clips/{clip_id}/auto-sfx", json={"max_items": 1})

    assert [i["id"] for i in first.json()["tracks"]["sfx"]] == [
        "mine",
        "auto-sfx-1",
        "auto-sfx-2",
    ]
    assert [i["id"] for i in again.json()["tracks"]["sfx"]] == ["mine", "auto-sfx-1"]


def test_a_clip_that_needs_no_sound_loses_its_auto_items(
    data_dir: Path, sample_mp4: Path
) -> None:
    llm = FakeLLMClient(REPLY, json.dumps({"sounds": []}))
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        clip_id = seed_clip(client.app.state.engine, sample_mp4)  # type: ignore[attr-defined]
        url = f"/api/clips/{clip_id}/auto-sfx"

        assert len(client.post(url, json={}).json()["tracks"]["sfx"]) == 2
        response = client.post(url, json={})

    assert response.status_code == 200
    assert response.json()["tracks"]["sfx"] == []


def test_auto_sfx_errors(
    llm_client: tuple[TestClient, Engine], sample_mp4: Path
) -> None:
    client, engine = llm_client
    clip_id = seed_clip(engine, sample_mp4)
    rendering = seed_clip(engine, sample_mp4, "rendering")
    no_work = add_clip(engine, add_project(engine), "candidate", 80)

    assert_error(client.post("/api/clips/42/auto-sfx", json={}), 404, "not_found")
    assert_error(
        client.post(f"/api/clips/{no_work}/auto-sfx", json={}), 409, "conflict"
    )
    assert_error(
        client.post(f"/api/clips/{rendering}/auto-sfx", json={}), 409, "conflict"
    )
    for body in ({"max_items": 0}, {"max_items": 99}, {"other": 1}):
        url = f"/api/clips/{clip_id}/auto-sfx"
        assert_error(client.post(url, json=body), 422, "validation_error")
    assert client.get(f"/api/clips/{clip_id}").json()["tracks"]["sfx"] == []


@pytest.mark.parametrize("llm", [FailingLLM(), FakeLLMClient("{}", repeat_last=True)])
def test_auto_sfx_answers_502_when_the_llm_fails(
    llm_client: tuple[TestClient, Engine], sample_mp4: Path
) -> None:
    client, engine = llm_client
    clip_id = seed_clip(engine, sample_mp4)

    response = client.post(f"/api/clips/{clip_id}/auto-sfx", json={})

    assert_error(response, 502, "llm_error")
    assert client.get(f"/api/clips/{clip_id}").json()["tracks"]["sfx"] == []
