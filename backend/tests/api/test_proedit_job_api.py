"""Tests of the "proedit" job and the estimate (SPEC-v3 3.8, 1.6) through
the API: a start runs to a rendered variant with the plan, notes and
progress steps while the original stays as it was; a failed run fails its
variant; the estimate calls no LLM; agents may run Pro Edit but posting
stays human-only."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from api_key_fakes import make_key
from apihelpers import assert_error
from clipforge import jobs
from clipforge.db import JobRow
from clipforge.job_progress import steps_of
from clipforge.proedit import run_job
from clipforge.proedit.director_result import DirectorResult
from clipforge.proedit.run_job import run_proedit_job
from clipforge.proedit.snap import PlanNote
from fastapi.testclient import TestClient
from proedit_run_fakes import (
    OfflineLLM,
    Processed,
    clip_of,
    no_face_models,
    processed_clip,
)
from sqlalchemy import Engine
from sqlmodel import Session

API = "/api/proedit"


@pytest.fixture
def original(
    api_engine: Engine, sample_mp4: Path, monkeypatch: pytest.MonkeyPatch
) -> Processed:
    no_face_models(monkeypatch)
    return processed_clip(api_engine, sample_mp4)


def test_a_start_job_plans_and_renders_the_variant_only(
    client: TestClient, api_engine: Engine, original: Processed
) -> None:
    before = clip_of(api_engine, original.clip_id)
    started = client.post(f"{API}/clips/{original.clip_id}/runs").json()
    claimed = jobs.claim_next(api_engine)
    assert claimed is not None and claimed.id == started["job_id"]

    jobs.run_claimed(api_engine, claimed, llm=OfflineLLM())

    run = client.get(f"{API}/runs/{started['run']['id']}").json()
    assert run["status"] == "done", run
    assert run["plan_id"] is not None and run["finished_at"] is not None
    assert any("offline" in note for note in run["notes"]), run["notes"]
    assert any("images" in note for note in run["notes"]), run["notes"]
    assert run["rounds"] == 0 and run["cost_actual"] is None
    variant_id = started["clip"]["id"]
    plan = client.get(f"{API}/clips/{variant_id}/plan").json()
    assert plan["id"] == run["plan_id"] and plan["created_by"] == "rule_director"
    variant = clip_of(api_engine, variant_id)
    assert variant.status == "rendered"
    assert variant.output_path is not None and Path(variant.output_path).is_file()
    assert clip_of(api_engine, original.clip_id) == before
    with Session(api_engine) as session:
        job = session.get_one(JobRow, started["job_id"])
        assert (job.status, job.progress, job.step) == ("done", 1.0, "final")
    assert steps_of("proedit") == ("plan", "proxy", "critic", "final")


def test_the_items_the_director_moved_or_dropped_are_run_notes(
    client: TestClient,
    api_engine: Engine,
    original: Processed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    director_plan = run_job.director_plan

    def with_notes(*args: Any, **kwargs: Any) -> DirectorResult:
        result = director_plan(*args, **kwargs)
        dropped = PlanNote(9, "shake", "dropped", "over the budget", 16.367)
        moved = PlanNote(4, "sfx", "moved", "off the punchline", 2.5)
        return replace(result, notes=[dropped, moved])

    monkeypatch.setattr(run_job, "director_plan", with_notes)
    started = client.post(f"{API}/clips/{original.clip_id}/runs").json()
    claimed = jobs.claim_next(api_engine)
    assert claimed is not None

    jobs.run_claimed(api_engine, claimed, llm=OfflineLLM())

    run = client.get(f"{API}/runs/{started['run']['id']}").json()
    edits = [n for n in run["notes"] if n.startswith(("Moved", "Dropped"))]
    assert edits == [
        "Moved sfx at 2.50 s: off the punchline",
        "Dropped shake at 16.37 s: over the budget",
    ]


def test_a_failed_run_fails_its_variant_and_frees_it(
    client: TestClient,
    api_engine: Engine,
    original: Processed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = client.post(
        f"{API}/clips/{original.clip_id}/runs", json={"use_critic": False}
    ).json()

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("ffmpeg broke")

    monkeypatch.setattr(run_job, "render_final", broken)
    with pytest.raises(RuntimeError, match="ffmpeg broke"):
        run_proedit_job(api_engine, started["job_id"], llm=OfflineLLM())

    run = client.get(f"{API}/runs/{started['run']['id']}").json()
    assert (run["status"], run["error"]) == ("failed", "ffmpeg broke")
    assert clip_of(api_engine, started["clip"]["id"]).status == "failed"
    rerender = client.post(f"{API}/clips/{started['clip']['id']}/render")
    assert rerender.status_code == 202, rerender.text


def test_the_estimate_prices_the_director_and_the_critic_rounds(
    client: TestClient, original: Processed
) -> None:
    url = f"{API}/clips/{original.clip_id}/estimate"

    with_critic = client.get(url, params={"preset": "phonk_edit"})
    without = client.get(url, params={"use_critic": "false"})

    assert with_critic.status_code == 200, with_critic.text
    estimate = with_critic.json()
    assert estimate["director_tokens"] > 0
    assert estimate["critic_rounds"] == 2
    assert estimate["critic_tokens"] > 0
    assert estimate["text"]
    assert without.json()["critic_rounds"] == 0
    assert without.json()["critic_tokens"] == 0
    missing = client.get(url, params={"music": "nope"})
    assert_error(missing, 422, "invalid_options")
    assert client.get(url, params={"preset": "nope"}).status_code == 422
    assert_error(client.get(f"{API}/clips/999/estimate"), 404, "not_found")


def test_the_status_says_how_many_critic_rounds_a_run_makes(
    client: TestClient,
) -> None:
    assert client.get(f"{API}/status").json() == {
        "enabled": True,
        "critic_max_rounds": 2,
    }


def test_an_agent_may_run_pro_edit_but_not_approve_the_variant(
    client: TestClient, original: Processed
) -> None:
    key = {"X-API-Key": make_key(client)}

    started = client.post(f"/api/v1/proedit/clips/{original.clip_id}/runs", headers=key)
    estimate = client.get(
        f"/api/v1/proedit/clips/{original.clip_id}/estimate", headers=key
    )

    assert started.status_code == 202, started.text
    assert estimate.status_code == 200, estimate.text
    variant_id = started.json()["clip"]["id"]
    runs = client.get(f"/api/v1/proedit/clips/{variant_id}/runs", headers=key)
    assert runs.status_code == 200
    post = client.post(
        f"/api/clips/{variant_id}/quick-post",
        json={"platforms": ["youtube"]},
        headers=key,
    )
    assert_error(post, 403, "human_only")
