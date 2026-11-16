"""Tests of the Pro Edit run endpoints (SPEC-v3 3.8) without running the
jobs: a start makes a variant and queues its "proedit" job, the runs, the
plan versions, the editor's patch and reset, the jobs that regenerate,
re-run the critic and render, and their errors (404 and 422 on every
endpoint). The jobs themselves are in test_proedit_job_api.py."""

from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge.db import JobRow
from clipforge.proedit.rows import ProEditRunRow
from fastapi.testclient import TestClient
from proedit_run_fakes import Processed, clip_of, processed_clip, store_plan, zoom
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session, select

API = "/api/proedit"


@pytest.fixture
def original(api_engine: Engine, sample_mp4: Path) -> Processed:
    return processed_clip(api_engine, sample_mp4)


def start(client: TestClient, clip_id: int, **options: object) -> dict[str, object]:
    response = client.post(f"{API}/clips/{clip_id}/runs", json=options or None)
    assert response.status_code == 202, response.text
    started: dict[str, object] = response.json()
    return started


def finish_runs(engine: Engine, clip_id: int) -> None:
    """Mark every run of clip clip_id done, as a finished job leaves them."""
    with Session(engine) as session:
        rows = session.exec(
            select(ProEditRunRow).where(ProEditRunRow.clip_id == clip_id)
        )
        for run in rows:
            run.status = "done"
            session.add(run)
        session.commit()


def test_a_start_makes_a_variant_and_queues_its_job(
    client: TestClient, api_engine: Engine, original: Processed
) -> None:
    before = clip_of(api_engine, original.clip_id)

    started = start(client, original.clip_id, preset="phonk_edit", use_critic=False)

    clip, run = started["clip"], started["run"]
    assert isinstance(clip, dict) and isinstance(run, dict)
    assert clip["id"] != original.clip_id
    assert clip["parent_clip_id"] == original.clip_id
    assert clip["variant"] == "pro_edit"
    assert clip["title"] == "Pizza night — Pro Edit"
    assert clip["status"] == "rendering"
    assert (clip["start"], clip["end"]) == (before.start, before.end)
    assert run["status"] == "queued" and run["mode"] == "start"
    assert run["options"]["preset"] == "phonk_edit"
    assert run["job_id"] == started["job_id"]
    with Session(api_engine) as session:
        job = session.get_one(JobRow, started["job_id"])
        assert (job.kind, job.status, job.clip_id) == ("proedit", "queued", clip["id"])
    assert clip_of(api_engine, original.clip_id) == before
    runs = client.get(f"{API}/clips/{clip['id']}/runs").json()
    assert [r["id"] for r in runs] == [run["id"]]
    assert client.get(f"{API}/runs/{run['id']}").json() == run


def test_a_start_refuses_a_variant_missing_options_and_a_missing_clip(
    client: TestClient, original: Processed
) -> None:
    variant = start(client, original.clip_id)["clip"]
    assert isinstance(variant, dict)

    again = client.post(f"{API}/clips/{variant['id']}/runs")
    recipe = client.post(
        f"{API}/clips/{original.clip_id}/runs", json={"style_recipe_id": 999}
    )
    music = client.post(f"{API}/clips/{original.clip_id}/runs", json={"music": "nope"})
    extra = client.post(f"{API}/clips/{original.clip_id}/runs", json={"llm": "x"})

    assert_error(again, 422, "not_an_original")
    assert_error(recipe, 422, "invalid_options")
    assert_error(music, 422, "invalid_options")
    assert extra.status_code == 422
    assert_error(client.post(f"{API}/clips/999/runs"), 404, "not_found")
    assert_error(client.get(f"{API}/runs/999"), 404, "not_found")


def test_a_clip_of_an_unprocessed_project_cannot_start(
    client: TestClient, api_engine: Engine, original: Processed
) -> None:
    other = add_clip(api_engine, add_project(api_engine), "candidate", 50)

    assert_error(client.post(f"{API}/clips/{other}/runs"), 409, "conflict")


def test_jobs_on_a_variant_need_a_plan_and_one_at_a_time(
    client: TestClient, api_engine: Engine, original: Processed
) -> None:
    variant = start(client, original.clip_id)["clip"]
    assert isinstance(variant, dict)
    vid = variant["id"]

    assert_error(client.post(f"{API}/clips/{vid}/regenerate"), 409, "proedit_busy")
    finish_runs(api_engine, vid)
    assert_error(client.post(f"{API}/clips/{vid}/critic"), 409, "no_plan")
    assert_error(client.post(f"{API}/clips/{vid}/render"), 409, "no_plan")
    store_plan(api_engine, vid, zoom(1, 0.5))

    for mode in ("render", "critic", "regenerate"):
        response = client.post(f"{API}/clips/{vid}/{mode}")
        assert response.status_code == 202, response.text
        run = response.json()["run"]
        assert run["mode"] == mode
        assert run["options"]["preset"] == "clean_pro"
        finish_runs(api_engine, vid)
    assert [r["mode"] for r in client.get(f"{API}/clips/{vid}/runs").json()] == [
        "regenerate",
        "critic",
        "render",
        "start",
    ]
    original_id = original.clip_id
    for mode in ("render", "critic", "regenerate", "reset"):
        response = client.post(f"{API}/clips/{original_id}/{mode}")
        assert_error(response, 422, "not_a_proedit_variant")
    assert_error(client.post(f"{API}/clips/999/render"), 404, "not_found")


def test_the_plan_versions_the_patch_and_the_reset(
    client: TestClient, api_engine: Engine, original: Processed
) -> None:
    variant = start(client, original.clip_id)["clip"]
    assert isinstance(variant, dict)
    vid = variant["id"]
    finish_runs(api_engine, vid)
    assert_error(client.get(f"{API}/clips/{vid}/plan"), 404, "no_plan")
    assert_error(client.post(f"{API}/clips/{vid}/reset"), 409, "no_plan")
    first = store_plan(api_engine, vid, zoom(1, 0.5), zoom(2, 1.5))
    kept = first.items[0].model_dump(mode="json")
    moved = zoom(2, 1.8).model_dump(mode="json")
    added = zoom(3, 1.0, scale=1.3).model_dump(mode="json")

    patched = client.patch(
        f"{API}/clips/{vid}/plan", json={"items": [kept, moved, added]}
    )

    assert patched.status_code == 200, patched.text
    plan = patched.json()
    assert (plan["version"], plan["created_by"]) == (2, "user")
    assert [(i["id"], i["source"]) for i in plan["items"]] == [
        (1, "auto"),
        (2, "manual"),
        (3, "manual"),
    ]
    assert client.get(f"{API}/clips/{vid}/plan").json() == plan
    reset = client.post(f"{API}/clips/{vid}/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["version"] == 3
    assert reset.json()["items"] == [i.model_dump(mode="json") for i in first.items]
    versions = client.get(f"{API}/clips/{vid}/plans").json()
    assert [v["version"] for v in versions] == [1, 2, 3]
    assert client.get(f"{API}/clips/{vid}/runs").json()[0]["mode"] == "start"


def test_a_patch_with_invalid_items_lists_the_problems(
    client: TestClient, api_engine: Engine, original: Processed
) -> None:
    variant = start(client, original.clip_id)["clip"]
    assert isinstance(variant, dict)
    vid = variant["id"]
    busy = client.patch(f"{API}/clips/{vid}/plan", json={"items": []})
    finish_runs(api_engine, vid)
    store_plan(api_engine, vid, zoom(1, 0.5))
    bad = [
        zoom(1, 0.5, scale=2.0).model_dump(mode="json"),
        zoom(2, 9.0).model_dump(mode="json"),
    ]

    response = client.patch(f"{API}/clips/{vid}/plan", json={"items": bad})

    assert_error(busy, 409, "proedit_busy")
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_plan"
    assert len(body["problems"]) >= 2
    assert any("item 2" in p for p in body["problems"]), body["problems"]
    assert [v["version"] for v in client.get(f"{API}/clips/{vid}/plans").json()] == [1]
    assert_error(
        client.patch(f"{API}/clips/999/plan", json={"items": []}), 404, "not_found"
    )


ENDPOINTS = [
    ("GET", "/clips/{id}/variants", None),
    ("POST", "/clips/{id}/runs", None),
    ("GET", "/runs/{id}", None),
    ("GET", "/clips/{id}/runs", None),
    ("GET", "/clips/{id}/plan", None),
    ("GET", "/clips/{id}/plans", None),
    ("PATCH", "/clips/{id}/plan", {"items": []}),
    ("POST", "/clips/{id}/reset", None),
    ("POST", "/clips/{id}/regenerate", None),
    ("POST", "/clips/{id}/critic", None),
    ("POST", "/clips/{id}/render", None),
    ("GET", "/clips/{id}/estimate", None),
]


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_every_endpoint_answers_404_for_a_missing_id_and_422_for_a_bad_one(
    client: TestClient, method: str, path: str, body: object
) -> None:
    missing = client.request(method, API + path.format(id=999), json=body)
    bad = client.request(method, API + path.format(id="x"), json=body)

    assert_error(missing, 404, "not_found")
    assert bad.status_code == 422
    assert bad.json()["error"] == "validation_error"
