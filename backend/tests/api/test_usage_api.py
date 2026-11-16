"""GET /api/usage and the monthly caps that refuse new jobs (SPEC-v2 2.4)."""

import json
from pathlib import Path

import httpx
from apihelpers import assert_error
from clipforge import usage
from clipforge.api.app import create_app
from clipforge.usage import COMPUTE, LLM_TOKENS, record
from fakes import FakeLLMClient, openai_reply
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine

URL = "https://www.youtube.com/watch?v=abc"
NEW_TEXT = {
    "title": "Yoga told me to listen",
    "description": "A body with one question.",
    "hashtags": ["yoga", "standup", "comedy"],
}


def kinds(client: TestClient, query: str = "") -> dict[str, dict[str, object]]:
    response = client.get(f"/api/usage{query}")
    assert response.status_code == 200
    return {item["kind"]: item for item in response.json()["kinds"]}


def test_an_empty_month_has_zero_totals_and_no_caps(client: TestClient) -> None:
    body = client.get("/api/usage").json()

    assert body["projects"] == []
    assert [
        (k["kind"], k["units"], k["cap"], k["exceeded"]) for k in body["kinds"]
    ] == [
        ("compute", 0, None, False),
        ("llm_tokens", 0, None, False),
        ("api_calls", 0, None, False),
    ]
    assert body["month"] == usage.utc_now().strftime("%Y-%m")


def test_totals_per_month_kind_and_project(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    record(api_engine, COMPUTE, 90, project_id=project_id)
    record(api_engine, LLM_TOKENS, 500, project_id=project_id)
    record(api_engine, LLM_TOKENS, 250)
    record(
        api_engine,
        COMPUTE,
        1,
        project_id=project_id,
        at=usage.utc_now().replace(year=2020, month=1, day=15),
    )

    now = client.get("/api/usage").json()
    january = client.get("/api/usage?month=2020-01").json()

    assert {k["kind"]: k["units"] for k in now["kinds"]} == {
        "compute": 90,
        "llm_tokens": 750,
        "api_calls": 0,
    }
    assert {(p["project_id"], p["kind"]): p["units"] for p in now["projects"]} == {
        (None, "llm_tokens"): 250,
        (project_id, "compute"): 90,
        (project_id, "llm_tokens"): 500,
    }
    assert january["month"] == "2020-01"
    assert january["kinds"][0]["units"] == 1


def test_an_invalid_month_is_a_422(client: TestClient) -> None:
    assert_error(client.get("/api/usage?month=2026-13"), 422, "validation_error")
    assert_error(client.get("/api/usage?month=october"), 422, "validation_error")


def test_the_settings_caps_show_in_the_totals(client: TestClient) -> None:
    client.put(
        "/api/settings", json={"usage_cap_compute_hours": 2, "usage_cap_llm_tokens": 9}
    )

    totals = kinds(client)

    assert totals["compute"]["cap"] == 7200
    assert totals["llm_tokens"]["cap"] == 9
    assert totals["api_calls"]["cap"] is None
    saved = client.get("/api/settings").json()
    assert (saved["usage_cap_compute_hours"], saved["usage_cap_api_calls"]) == (2, 0)


def test_a_cap_must_not_be_negative(client: TestClient) -> None:
    response = client.put("/api/settings", json={"usage_cap_llm_tokens": -1})

    assert response.status_code == 422


def test_new_jobs_are_refused_once_a_cap_is_used_up(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    client.put("/api/settings", json={"usage_cap_compute_hours": 0.01})
    record(api_engine, COMPUTE, 30, project_id=project_id)
    assert client.post("/api/projects", json={"url": URL}).status_code == 201
    record(api_engine, COMPUTE, 7, project_id=project_id)

    refused = client.post("/api/projects", json={"url": URL})

    message = assert_error(refused, 409, "usage_cap_exceeded")
    assert "cap of 0.01 compute hours" in message and "Settings" in message
    assert len(client.get("/api/projects").json()) == 2


def test_an_upload_is_refused_before_the_file_is_saved(
    client: TestClient, api_engine: Engine, data_dir: Path
) -> None:
    client.put("/api/settings", json={"usage_cap_llm_tokens": 100})
    record(api_engine, LLM_TOKENS, 100)

    response = client.post(
        "/api/projects/upload", files={"file": ("talk.mp4", b"video", "video/mp4")}
    )

    assert_error(response, 409, "usage_cap_exceeded")
    assert not (data_dir / "uploads").exists()
    assert client.get("/api/projects").json() == []


def test_a_render_is_refused_and_works_again_without_the_cap(
    client: TestClient, api_engine: Engine, data_dir: Path, sample_mp4: Path
) -> None:
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    clip_id = add_clip(api_engine, project_id, "candidate", 80, "Pizza")
    client.put("/api/settings", json={"usage_cap_llm_tokens": 10})
    record(api_engine, LLM_TOKENS, 10)

    refused = client.post(f"/api/clips/{clip_id}/render")
    client.put("/api/settings", json={"usage_cap_llm_tokens": 0})
    allowed = client.post(f"/api/clips/{clip_id}/render")

    assert_error(refused, 409, "usage_cap_exceeded")
    assert allowed.status_code == 202


def test_last_months_use_does_not_block_this_month(
    client: TestClient, api_engine: Engine
) -> None:
    client.put("/api/settings", json={"usage_cap_llm_tokens": 10})
    record(api_engine, LLM_TOKENS, 1000, at=usage.utc_now().replace(year=2020))

    assert client.post("/api/projects", json={"url": URL}).status_code == 201


class CountingLLM(FakeLLMClient):
    """A fake LLM that reports 42 tokens per call, as the real clients do."""

    def complete_json(self, system: str, user: str) -> str:
        usage.record_tokens(42)
        return super().complete_json(system, user)


def test_regenerate_text_records_its_tokens_for_the_clips_project(
    data_dir: Path, sample_mp4: Path
) -> None:
    llm = CountingLLM(json.dumps(NEW_TEXT))
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
        project_id = add_project(engine)
        add_work(engine, project_id, sample_mp4)
        clip_id = add_clip(engine, project_id, "candidate", 80, "Pizza")

        assert client.post(f"/api/clips/{clip_id}/regenerate-text").status_code == 200

        projects = client.get("/api/usage").json()["projects"]
    assert projects == [
        {"project_id": project_id, "kind": "llm_tokens", "units": 42, "cost_usd": None}
    ]


def test_the_connection_test_records_tokens_outside_any_project(
    data_dir: Path,
) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=openai_reply('{"ok": true}', tokens=(30, 3)))

    app = create_app(
        run_worker=False,
        caption_previews=False,
        llm_transport=httpx.MockTransport(answer),
    )
    with TestClient(app) as client:
        client.put(
            "/api/settings",
            json={
                "llm_provider": "openai",
                "openai_base_url": "https://llm.example/v1",
                "openai_api_key": "k",
            },
        )

        assert client.post("/api/settings/test-llm").json()["ok"] is True

        assert client.get("/api/usage").json()["projects"] == [
            {"project_id": None, "kind": "llm_tokens", "units": 33, "cost_usd": None}
        ]
