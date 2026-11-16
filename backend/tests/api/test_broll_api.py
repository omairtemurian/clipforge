"""Tests of B-roll through the API (SPEC-v2 3.6, api/broll): the LLM (mocked)
picks sentences and keywords of a saved clip and each spot is listed for
review with the stock videos Pexels has for it (respx recorded answers, no
network); a stock video is downloaded into the asset library with its
license and attribution and put on the broll track as a full-screen
cutaway or a picture-in-picture, replaced and removed; errors answer 404,
409, 422 or 502."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from apihelpers import assert_error
from clipforge import config, usage
from clipforge.api.app import create_app
from clipforge.asset_rows import UsageRecordRow
from clipforge.assets import add_asset, get_asset
from clipforge.ffmpeg import run_ffmpeg
from clipforge.llm_http import LLMError
from clipforge.stock import pexels, pixabay
from fakes import FIXTURES, FakeLLMClient
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session, select

# Sentences of clip 0.5-34.35 s: 1 "So, I tried yoga." (1.03-2.4 s), 4 "Then
# I bought one of those smart fridges." (16.4-19.2 s).
REPLY = json.dumps(
    {
        "spots": [
            {"sentence": 4, "keywords": ["smart fridge", "kitchen"]},
            {"sentence": 1, "keywords": ["yoga class"]},
        ]
    }
)
PORTRAIT_CDN = "https://player.vimeo.com/external/342571552.hd.mp4"


class FailingLLM:
    """An LLM that cannot be reached."""

    def complete_json(self, system: str, user: str) -> str:
        raise LLMError("POST https://llm.test/chat/completions failed: refused")


def recorded_search() -> dict[str, Any]:
    """Return the recorded Pexels video search answer."""
    body: dict[str, Any] = json.loads(
        (FIXTURES / "stock" / "pexels_search.json").read_text(encoding="utf-8")
    )
    return body


@pytest.fixture(scope="module")
def stock_mp4(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    """The bytes of a 2 s red 90x160 H.264 video (the CDN's file)."""
    path = tmp_path_factory.mktemp("cdn") / "clip.mp4"
    run_ffmpeg(
        ["-f", "lavfi", "-i", "color=c=red:size=90x160:rate=30:duration=2"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", path]
    )
    return path.read_bytes()


@pytest.fixture
def pexels_on(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> None:
    """Pexels has an API key, Pixabay has none."""
    keys = {"pexels_api_key": "pexels-secret", "pixabay_api_key": ""}
    monkeypatch.setattr(config, "settings", config.settings.model_copy(update=keys))
    pixabay.cache.clear()


@pytest.fixture
def llm() -> FakeLLMClient:
    """An LLM that picks the yoga and the fridge sentences."""
    return FakeLLMClient(REPLY, repeat_last=True)


@pytest.fixture
def llm_client(
    pexels_on: None, llm: FakeLLMClient
) -> Iterator[tuple[TestClient, Engine]]:
    """A client of an app that asks llm, and its engine."""
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        yield client, client.app.state.engine  # type: ignore[attr-defined]


@pytest.fixture
def stock_routes(respx_mock: respx.MockRouter, stock_mp4: bytes) -> respx.Route:
    """Pexels answers every search with the recorded answer and its CDN
    serves stock_mp4; return the search route."""
    respx_mock.get(url__startswith=PORTRAIT_CDN).mock(
        return_value=httpx.Response(200, content=stock_mp4)
    )
    return respx_mock.get(pexels.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=recorded_search())
    )


def seed_clip(engine: Engine, sample_mp4: Path, status: str = "candidate") -> int:
    """Add a project processed from the fixture and its clip 0.5-34.35 s
    with status; return the clip's id."""
    project_id = add_project(engine)
    add_work(engine, project_id, sample_mp4)
    return add_clip(engine, project_id, status, 80, start=0.5, end=34.35)


def portrait_stock(client: TestClient, clip_id: int) -> dict[str, Any]:
    """Return the portrait stock video that the clip's first spot found."""
    spots = client.post(f"/api/clips/{clip_id}/broll/spots", json={}).json()
    return next(r for r in spots[0]["results"] if r["height"] > r["width"])


@pytest.mark.respx(assert_all_called=False)
def test_spots_are_the_llms_sentences_with_stock_results(
    llm_client: tuple[TestClient, Engine],
    llm: FakeLLMClient,
    stock_routes: respx.Route,
    sample_mp4: Path,
) -> None:
    client, engine = llm_client
    clip_id = seed_clip(engine, sample_mp4)

    response = client.post(f"/api/clips/{clip_id}/broll/spots", json={})

    assert response.status_code == 200
    spots = response.json()
    assert [(s["sentence"], s["start"], s["end"], s["query"]) for s in spots] == [
        (1, 1.03, 2.53, "yoga class"),
        (4, 16.4, 19.2, "smart fridge kitchen"),
    ]
    assert spots[0]["text"] == "So, I tried yoga."
    assert [r["provider_id"] for r in spots[0]["results"]] == ["1448735", "2499611"]
    assert spots[0]["results"][0]["license"] == "Pexels License"
    assert spots[0]["error"] is None
    params = [dict(call.request.url.params) for call in stock_routes.calls]
    assert [(p["query"], p["orientation"]) for p in params] == [
        ("yoga class", "portrait"),
        ("smart fridge kitchen", "portrait"),
    ]
    [(system, user)] = llm.calls
    assert "B-roll" in system and "4: 16.40s-19.20s Then I bought" in user
    with Session(engine) as session:
        calls = session.exec(
            select(UsageRecordRow).where(UsageRecordRow.kind == usage.API_CALLS)
        ).all()
    assert len(calls) == 2
    assert client.get(f"/api/clips/{clip_id}").json()["tracks"]["broll"] == []


@pytest.mark.respx(assert_all_called=False)
def test_pip_spots_search_landscape_and_a_failed_search_is_the_spots_error(
    llm_client: tuple[TestClient, Engine],
    respx_mock: respx.MockRouter,
    sample_mp4: Path,
) -> None:
    client, engine = llm_client
    clip_id = seed_clip(engine, sample_mp4)
    route = respx_mock.get(pexels.SEARCH_URL).mock(
        side_effect=[
            httpx.Response(200, json=recorded_search()),
            httpx.Response(500, text="oops"),
        ]
    )

    spots = client.post(
        f"/api/clips/{clip_id}/broll/spots", json={"mode": "pip", "max_spots": 2}
    ).json()

    assert route.calls[0].request.url.params["orientation"] == "landscape"
    assert len(spots[0]["results"]) == 2 and spots[0]["error"] is None
    assert spots[1]["results"] == [] and "500" in spots[1]["error"]


@pytest.mark.respx(assert_all_called=False)
def test_a_stock_video_goes_on_the_broll_track_and_is_replaced_and_removed(
    llm_client: tuple[TestClient, Engine], stock_routes: respx.Route, sample_mp4: Path
) -> None:
    client, engine = llm_client
    clip_id = seed_clip(engine, sample_mp4)
    found = portrait_stock(client, clip_id)

    cutaway = client.post(
        f"/api/clips/{clip_id}/broll",
        json={"stock": found, "start": 16.4, "end": 19.2},
    )
    pip = client.post(
        f"/api/clips/{clip_id}/broll",
        json={"stock": found, "start": 1.03, "end": 2.53, "mode": "pip", "y": 0.25},
    )

    assert cutaway.status_code == 200 and pip.status_code == 200
    first, second = pip.json()["tracks"]["broll"]
    # The stock video lasts 2 s: the cutaway ends with it.
    assert (first["id"], first["kind"], first["start"], first["end"]) == (
        "broll-1",
        "video",
        16.4,
        18.4,
    )
    assert first["props"] == {
        "offset": 0.0, "mode": "cutaway", "x": 0.5, "y": 0.3, "width": 0.8
    }  # fmt: skip
    assert (second["id"], second["start"], second["end"]) == ("broll-2", 1.03, 2.53)
    assert second["props"]["mode"] == "pip" and second["props"]["y"] == 0.25
    assert first["asset_id"] == second["asset_id"]
    with Session(engine) as session:
        asset = get_asset(session, first["asset_id"])
        assert asset is not None
        image = add_asset(session, "image", str(sample_mp4), "CC0-1.0").id
    assert asset.license == "Pexels License"
    assert asset.source_url == "https://www.pexels.com/video/2499611/"
    assert "Pexels" in asset.attribution
    assert asset.tags[:2] == ["stock", "pexels"]

    replaced = client.put(
        f"/api/clips/{clip_id}/broll/broll-2", json={"asset_id": image}
    ).json()["tracks"]["broll"][1]
    removed = client.delete(f"/api/clips/{clip_id}/broll/broll-1").json()

    assert (replaced["kind"], replaced["asset_id"]) == ("image", image)
    assert (replaced["start"], replaced["end"]) == (1.03, 2.53)
    assert replaced["props"]["mode"] == "pip" and replaced["props"]["y"] == 0.25
    assert [i["id"] for i in removed["tracks"]["broll"]] == ["broll-2"]
    history = client.get(f"/api/clips/{clip_id}/versions").json()
    assert len(history["versions"]) >= 4


@pytest.mark.respx(assert_all_called=False)
def test_search_finds_other_footage(
    llm_client: tuple[TestClient, Engine], stock_routes: respx.Route
) -> None:
    client, _ = llm_client

    found = client.get(
        "/api/broll/search",
        params={"query": "ocean", "orientation": "landscape", "min_seconds": 10},
    )
    providers = client.get("/api/broll/providers").json()

    assert [clip["provider_id"] for clip in found.json()] == ["1448735"]
    assert stock_routes.calls.last.request.url.params["query"] == "ocean"
    assert [(p["provider"], p["enabled"]) for p in providers] == [
        ("pexels", True),
        ("pixabay", False),
    ]
    assert_error(
        client.get("/api/broll/search", params={"query": "x", "provider": "pixabay"}),
        409,
        "provider_disabled",
    )


def test_without_stock_keys_spots_answer_409(
    client: TestClient, sample_mp4: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys = {"pexels_api_key": "", "pixabay_api_key": ""}
    monkeypatch.setattr(config, "settings", config.settings.model_copy(update=keys))
    engine = client.app.state.engine  # type: ignore[attr-defined]
    clip_id = seed_clip(engine, sample_mp4)

    response = client.post(f"/api/clips/{clip_id}/broll/spots", json={})

    assert_error(response, 409, "provider_disabled")
    assert "PEXELS_API_KEY" in response.json()["message"]


def test_spot_errors(
    pexels_on: None, sample_mp4: Path, llm_client: tuple[TestClient, Engine]
) -> None:
    client, engine = llm_client
    clip_id = seed_clip(engine, sample_mp4)
    rendering = seed_clip(engine, sample_mp4, status="rendering")
    no_work = add_clip(engine, add_project(engine), "candidate", 80)

    assert_error(client.post("/api/clips/999/broll/spots", json={}), 404, "not_found")
    assert_error(
        client.post(f"/api/clips/{rendering}/broll/spots", json={}), 409, "conflict"
    )
    assert_error(
        client.post(f"/api/clips/{no_work}/broll/spots", json={}), 409, "conflict"
    )
    assert_error(
        client.post(f"/api/clips/{clip_id}/broll/spots", json={"max_spots": 0}),
        422,
        "validation_error",
    )
    with TestClient(create_app(run_worker=False, llm=FailingLLM())) as failing:
        assert_error(
            failing.post(f"/api/clips/{clip_id}/broll/spots", json={}),
            502,
            "llm_error",
        )


def test_insert_errors(llm_client: tuple[TestClient, Engine], sample_mp4: Path) -> None:
    client, engine = llm_client
    clip_id = seed_clip(engine, sample_mp4)
    with Session(engine) as session:
        video = add_asset(session, "video", str(sample_mp4), "CC0-1.0").id
        sound = add_asset(session, "audio", str(sample_mp4), "CC0-1.0").id
    url = f"/api/clips/{clip_id}/broll"

    def put(**body: Any) -> httpx.Response:
        return client.post(url, json={"start": 1.0, "end": 2.0} | body)

    assert_error(put(), 422, "validation_error")
    assert_error(put(asset_id=video, end=0.5), 422, "validation_error")
    assert_error(put(asset_id=9999), 404, "not_found")
    assert_error(put(asset_id=sound), 422, "validation_error")
    assert_error(put(asset_id=video, start=40.0, end=41.0), 422, "validation_error")
    assert_error(put(asset_id=video, mode="corner"), 422, "validation_error")
    assert_error(client.delete(f"/api/clips/{clip_id}/broll/broll-9"), 404, "not_found")
    assert_error(
        client.put(f"/api/clips/{clip_id}/broll/broll-9", json={"asset_id": video}),
        404,
        "not_found",
    )
    assert put(asset_id=video).status_code == 200
