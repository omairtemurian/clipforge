"""Tests of the Pro Edit audio library through the API (SPEC-v3 5.1, 5.6,
TASK-217, api/proedit_audio): Freesound searches and downloads with recorded
answers (respx, no network), the missing-key and license errors, and the
CC BY credits appended to a clip's description."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from apihelpers import assert_error
from clipforge import config
from clipforge.assets import add_asset, get_asset
from clipforge.ffmpeg import run_ffmpeg
from clipforge.proedit.audio import freesound
from clipforge.proedit.config import ProEditConfig
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "freesound"
PREFIX = "/api/proedit/audio/freesound"
CC_BY_PREVIEW = "https://cdn.freesound.org/previews/361/361492_77-hq.mp3"
CREDIT = (
    '"Whoosh Fast" by ejfortin on Freesound '
    "(https://freesound.org/people/ejfortin/sounds/361492/), CC BY"
)


def recorded(name: str) -> dict[str, Any]:
    """Return the recorded answer in tests/fixtures/freesound/<name>.json."""
    body: dict[str, Any] = json.loads(
        (FIXTURES / f"{name}.json").read_text(encoding="utf-8")
    )
    return body


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> str:
    """A configured Freesound key."""
    keyed = config.settings.model_copy(update={"freesound_api_key": "secret"})
    monkeypatch.setattr(config, "settings", keyed)
    return "secret"


@pytest.fixture(scope="module")
def preview_mp3(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    """The bytes of a short MP3, as a Freesound preview."""
    path = tmp_path_factory.mktemp("preview") / "p.mp3"
    run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=0.5", str(path)])
    return path.read_bytes()


def test_the_status_says_to_add_a_key_until_there_is_one(
    client: TestClient, key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get(PREFIX).json() == {"enabled": True, "message": ""}
    monkeypatch.setattr(
        config,
        "settings",
        config.settings.model_copy(update={"freesound_api_key": ""}),
    )

    body = client.get(PREFIX).json()

    assert body["enabled"] is False
    assert "Add a Freesound key" in body["message"]
    assert "FREESOUND_API_KEY" in body["message"]


def test_without_a_key_search_and_download_are_provider_disabled(
    client: TestClient,
) -> None:
    searched = client.get(f"{PREFIX}/search", params={"tags": "whoosh"})
    downloaded = client.post(f"{PREFIX}/download", json={"sound_id": 361492})

    for response in (searched, downloaded):
        assert "Add a Freesound key" in assert_error(response, 409, "provider_disabled")


def test_search_lists_the_cc0_and_cc_by_sounds(
    client: TestClient, key: str, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(freesound.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=recorded("search_whoosh"))
    )

    response = client.get(
        f"{PREFIX}/search",
        params={"tags": "whoosh, air", "q": "fast", "max_duration": 3, "limit": 20},
    )

    assert response.status_code == 200
    sounds = response.json()
    assert [(s["id"], s["license"]) for s in sounds] == [
        (76693, "CC0 1.0"),
        (361492, "CC BY"),
        (530012, "CC BY 4.0"),
        (530013, "CC0 1.0"),
    ]
    assert sounds[1]["attribution"] == CREDIT
    params = route.calls.last.request.url.params
    assert params["filter"].startswith("tag:whoosh tag:air duration:[0 TO 3] license:")
    assert params["page_size"] == "20"


def test_search_needs_a_tag_or_a_query_and_valid_tags(
    client: TestClient, key: str
) -> None:
    assert_error(client.get(f"{PREFIX}/search"), 422, "validation_error")
    assert_error(
        client.get(f"{PREFIX}/search", params={"tags": 'a" OR x'}),
        422,
        "validation_error",
    )


def test_a_refusing_freesound_is_a_stock_error(
    client: TestClient, key: str, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(freesound.SEARCH_URL).mock(return_value=httpx.Response(401))

    message = assert_error(
        client.get(f"{PREFIX}/search", params={"q": "pop"}), 502, "stock_error"
    )

    assert "refused the API key" in message


def test_a_download_stores_the_sound_with_its_license_data(
    client: TestClient,
    api_engine: Engine,
    key: str,
    respx_mock: respx.MockRouter,
    preview_mp3: bytes,
) -> None:
    respx_mock.get(f"{freesound.API_URL}/sounds/361492/").mock(
        return_value=httpx.Response(200, json=recorded("sound_cc_by"))
    )
    cdn = respx_mock.get(CC_BY_PREVIEW).mock(
        return_value=httpx.Response(200, content=preview_mp3)
    )

    response = client.post(
        f"{PREFIX}/download",
        json={"sound_id": 361492, "kind": "sfx", "category": "whoosh"},
    )

    assert response.status_code == 200
    asset = response.json()
    assert (asset["kind"], asset["license"], asset["category"]) == (
        "sfx",
        "CC BY",
        "whoosh",
    )
    assert asset["attribution"] == CREDIT
    assert asset["source_url"] == "https://freesound.org/people/ejfortin/sounds/361492/"
    assert asset["downloaded_at"] is not None
    assert Path(asset["path"]).read_bytes() == preview_mp3
    with Session(api_engine) as session:
        assert get_asset(session, asset["id"]) is not None
    again = client.post(f"{PREFIX}/download", json={"sound_id": 361492})
    assert again.json()["id"] == asset["id"]
    assert cdn.call_count == 1


def test_a_sound_that_is_not_cc0_or_cc_by_is_not_downloaded(
    client: TestClient, key: str, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{freesound.API_URL}/sounds/411089/").mock(
        return_value=httpx.Response(200, json=recorded("sound_by_nc"))
    )

    response = client.post(f"{PREFIX}/download", json={"sound_id": 411089})

    assert "not CC0 or CC BY" in assert_error(response, 422, "license_rejected")
    assert [c.request.url.host for c in respx_mock.calls] == ["freesound.org"]


def test_a_download_of_an_unknown_sound_or_kind_is_refused(
    client: TestClient, key: str, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{freesound.API_URL}/sounds/7/").mock(
        return_value=httpx.Response(404, json={"detail": "Not found."})
    )

    assert_error(
        client.post(f"{PREFIX}/download", json={"sound_id": 7}), 502, "stock_error"
    )
    assert_error(
        client.post(f"{PREFIX}/download", json={"sound_id": 7, "kind": "video"}),
        422,
        "validation_error",
    )
    assert_error(
        client.post(f"{PREFIX}/download", json={"sound_id": 0}), 422, "validation_error"
    )


def library_asset(engine: Engine, license: str, attribution: str) -> int:
    with Session(engine) as session:
        return add_asset(
            session, "sfx", "/x/a.mp3", license, attribution=attribution
        ).id


def test_cc_by_credits_are_appended_to_the_clip_description_once(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(
        api_engine, project_id, "rendered", 80, "Pizza", description="Best pizza"
    )
    by = library_asset(api_engine, "CC BY 4.0", CREDIT)
    zero = library_asset(api_engine, "CC0 1.0", "Zero by someone")
    path = f"/api/proedit/clips/{clip_id}/credits"

    response = client.post(path, json={"asset_ids": [by, zero]})

    assert response.status_code == 200
    body = response.json()
    assert body["credits"] == [CREDIT]
    assert body["clip"]["description"] == f"Best pizza\n\nSound credits:\n- {CREDIT}"
    again = client.post(path, json={"asset_ids": [by]})
    assert again.json()["clip"]["description"] == body["clip"]["description"]
    assert (
        client.get(f"/api/clips/{clip_id}").json()["description"]
        == (body["clip"]["description"])
    )


def test_credits_need_an_existing_clip_and_assets(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "rendered", 80, "Pizza")

    assert_error(
        client.post("/api/proedit/clips/99/credits", json={"asset_ids": [1]}),
        404,
        "not_found",
    )
    assert_error(
        client.post(f"/api/proedit/clips/{clip_id}/credits", json={"asset_ids": [99]}),
        404,
        "not_found",
    )
    assert_error(
        client.post(f"/api/proedit/clips/{clip_id}/credits", json={"asset_ids": []}),
        422,
        "validation_error",
    )


def test_the_audio_endpoints_answer_proedit_disabled_when_it_is_off(
    client: TestClient, key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    off = config.settings.model_copy(update={"proedit": ProEditConfig(enabled=False)})
    monkeypatch.setattr(config, "settings", off)

    assert_error(client.get(PREFIX), 404, "proedit_disabled")
    assert_error(client.get(f"{PREFIX}/search"), 404, "proedit_disabled")
    assert_error(
        client.post(f"{PREFIX}/download", json={"sound_id": 1}), 404, "proedit_disabled"
    )
    assert_error(
        client.post("/api/proedit/clips/1/credits", json={"asset_ids": [1]}),
        404,
        "proedit_disabled",
    )
