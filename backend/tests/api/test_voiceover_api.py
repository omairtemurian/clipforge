"""Tests of AI voiceover through the API (SPEC-v2 3.5, api/voiceover): the
voices of the installed engines are listed; a voiceover spoken by the fake
piper (tts_fakes) is put on a clip's voiceover track as an asset with the
voice's license, then moved, spoken again, re-voiced and deleted, each a
version of the clip; errors answer 404, 409, 422 or 502."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge import assets, config, engines
from clipforge.api.app import create_app
from clipforge.asset_rows import UsageRecordRow
from clipforge.models import ClipStatus
from clipforge.pipeline.voiceover import VOICEOVER_TAG
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session, select
from tts_fakes import (
    PIPER_MULTI,
    PIPER_VOICE,
    SECONDS_PER_CHAR,
    piper_runs,
    piper_settings,
)

VOICE = f"piper:{PIPER_VOICE}"
TEXT = "Here is what happened next."
SECONDS = round(len(TEXT) * SECONDS_PER_CHAR, 3)


@pytest.fixture
def tts_client(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Engine]]:
    """A client of an app whose voiceover engine is the fake piper (no
    Kokoro), and its engine."""
    fake = piper_settings(tmp_path)
    settings = config.settings.model_copy(
        update={"models_dir": fake.models_dir, "piper_bin": fake.piper_bin}
    )
    monkeypatch.setattr(config, "settings", settings)
    engines.clear_cache()
    with TestClient(create_app(run_worker=False, caption_previews=False)) as client:
        yield client, client.app.state.engine  # type: ignore[attr-defined]
    engines.clear_cache()


def seed_clip(engine: Engine, status: ClipStatus = "candidate") -> int:
    """Add a project and its 20 s clip with status; return the clip's id."""
    return add_clip(engine, add_project(engine), status, 80, start=0.0, end=20.0)


def add(client: TestClient, clip_id: int, **body: object) -> dict:  # type: ignore[type-arg]
    """POST a voiceover (TEXT by VOICE from 2 s unless body says) and
    return the response's JSON (asserting 200)."""
    response = client.post(
        f"/api/clips/{clip_id}/voiceover",
        json={"text": TEXT, "voice": VOICE, "start": 2.0, **body},
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_the_installed_voices_are_listed(
    tts_client: tuple[TestClient, Engine],
) -> None:
    client, _ = tts_client
    voices = client.get("/api/voices").json()

    assert [voice["id"] for voice in voices] == [
        f"piper:{PIPER_MULTI}:0",
        f"piper:{PIPER_MULTI}:1",
        VOICE,
    ]
    assert voices[2] == {
        "id": VOICE,
        "engine": "piper",
        "name": "test (en-US, medium)",
        "language": "en-US",
        "gender": None,
        "license": "CC0 (test)",
    }
    statuses = {s["name"]: s for s in client.get("/api/engines").json()}
    assert statuses["piper"]["installed"] and not statuses["kokoro"]["installed"]


def test_a_voiceover_is_spoken_onto_the_track_as_a_licensed_asset(
    tts_client: tuple[TestClient, Engine],
) -> None:
    client, engine = tts_client
    clip_id = seed_clip(engine)

    clip = add(client, clip_id, volume=0.8)
    second = add(client, clip_id, start=10.0, duck=False)

    first, other = second["tracks"]["voiceover"]
    assert clip["tracks"]["voiceover"] == [first]
    assert first == {
        "id": "voiceover-1",
        "kind": "audio",
        "asset_id": first["asset_id"],
        "start": 2.0,
        "end": 2.0 + SECONDS,
        "props": {
            "volume": 0.8,
            "offset": 0.0,
            "text": TEXT,
            "voice": VOICE,
            "speed": 1.0,
            "duck": True,
        },
    }
    assert (other["id"], other["start"], other["props"]["duck"]) == (
        "voiceover-2",
        10.0,
        False,
    )
    assert other["asset_id"] == first["asset_id"]
    assert len(piper_runs(Path(config.settings.piper_bin))) == 1
    with Session(engine) as session:
        asset = assets.get_asset(session, first["asset_id"])
        used = session.exec(select(UsageRecordRow)).all()
    assert asset is not None
    assert (asset.kind, asset.tags, asset.license) == (
        "audio",
        [VOICEOVER_TAG],
        "CC0 (test)",
    )
    assert "test (en-US, medium)" in asset.attribution
    assert [record.kind for record in used] == ["compute", "compute"]
    assert len(client.get(f"/api/clips/{clip_id}/versions").json()) >= 2


def test_a_voiceover_is_moved_respoken_and_deleted(
    tts_client: tuple[TestClient, Engine],
) -> None:
    client, engine = tts_client
    clip_id = seed_clip(engine)
    item = add(client, clip_id)["tracks"]["voiceover"][0]
    url = f"/api/clips/{clip_id}/voiceover/{item['id']}"

    moved = client.patch(url, json={"start": 5.0, "volume": 0.5, "duck": False})
    faster = client.patch(url, json={"speed": 1.25})
    worded = client.patch(
        url, json={"text": "Short.", "voice": f"piper:{PIPER_MULTI}:1"}
    )

    [after_move] = moved.json()["tracks"]["voiceover"]
    assert (after_move["start"], after_move["end"]) == (5.0, 5.0 + SECONDS)
    assert after_move["asset_id"] == item["asset_id"]
    assert after_move["props"]["volume"] == 0.5 and not after_move["props"]["duck"]
    [after_speed] = faster.json()["tracks"]["voiceover"]
    assert after_speed["end"] == pytest.approx(5.0 + SECONDS * 0.8, abs=0.002)
    assert after_speed["asset_id"] != item["asset_id"]
    assert after_speed["props"]["volume"] == 0.5
    [after_text] = worded.json()["tracks"]["voiceover"]
    assert after_text["props"]["text"] == "Short."
    assert after_text["end"] == pytest.approx(
        5.0 + 6 * SECONDS_PER_CHAR * 0.8, abs=0.002
    )
    runs = piper_runs(Path(config.settings.piper_bin))
    assert runs[-1][-2:] == ["-s", "1"] and len(runs) == 3

    deleted = client.delete(url)
    assert deleted.status_code == 200
    assert deleted.json()["tracks"]["voiceover"] == []
    undone = client.post(f"/api/clips/{clip_id}/undo").json()
    assert [i["id"] for i in undone["tracks"]["voiceover"]] == [item["id"]]


def test_voiceover_errors(tts_client: tuple[TestClient, Engine]) -> None:
    client, engine = tts_client
    clip_id = seed_clip(engine)
    rendering = seed_clip(engine, "rendering")
    url = f"/api/clips/{clip_id}/voiceover"
    body = {"text": TEXT, "voice": VOICE, "start": 1.0}

    assert_error(client.post("/api/clips/42/voiceover", json=body), 404, "not_found")
    assert_error(
        client.post(f"/api/clips/{rendering}/voiceover", json=body), 409, "conflict"
    )
    assert_error(
        client.post(url, json={**body, "voice": "kokoro:af_heart"}),
        409,
        "engine_not_installed",
    )
    for bad in (
        {**body, "voice": "piper:nobody"},
        {**body, "start": 19.5},
        {**body, "text": "   "},
        {**body, "speed": 2.5},
        {**body, "other": 1},
    ):
        assert_error(client.post(url, json=bad), 422, "validation_error")
    assert_error(client.post(url, json={**body, "text": "FAIL"}), 502, "engine_error")
    assert_error(client.patch(f"{url}/voiceover-9", json={}), 404, "not_found")
    assert_error(client.delete(f"{url}/voiceover-9"), 404, "not_found")
    item = add(client, clip_id)["tracks"]["voiceover"][0]
    assert_error(
        client.patch(f"{url}/{item['id']}", json={"start": 19.0}),
        422,
        "validation_error",
    )
    assert client.get(f"/api/clips/{clip_id}").json()["tracks"]["voiceover"] == [item]


def test_a_recording_cannot_be_respoken_without_text(
    tts_client: tuple[TestClient, Engine],
) -> None:
    client, engine = tts_client
    clip_id = seed_clip(engine)
    asset_id = add(client, clip_id)["tracks"]["voiceover"][0]["asset_id"]
    recording = {
        "id": "rec",
        "kind": "audio",
        "asset_id": asset_id,
        "start": 0,
        "end": 1,
    }
    client.patch(f"/api/clips/{clip_id}/tracks", json={"voiceover": [recording]})
    url = f"/api/clips/{clip_id}/voiceover/rec"

    assert_error(client.patch(url, json={"speed": 1.5}), 422, "validation_error")
    moved = client.patch(url, json={"start": 3.0}).json()["tracks"]["voiceover"]
    assert (moved[0]["start"], moved[0]["end"], moved[0]["props"]["text"]) == (
        3.0,
        4.0,
        None,
    )
