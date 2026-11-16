"""Tests of the style recipe editor endpoints (SPEC-v3 4.4, 4.5): the
metrics, targets and description after an analysis, editing, export
without media, import, and the style-match score of a rendered clip.
Downloads run the real yt-dlp on canned pages (style_fakes); the clip's
video is measured by a stand-in returning fixed features."""

import os
from pathlib import Path
from typing import Any

import pytest
from apihelpers import assert_error
from clipforge.models import ProEditPlan, StyleTargets
from clipforge.proedit.plan_store import save_plan
from clipforge.proedit.style import match
from clipforge.proedit.style.metrics import METRICS
from clipforge.proedit.style.recipe import aggregate, describe_rules
from fastapi.testclient import TestClient
from proedit_run_fakes import OfflineLLM, Processed, clip_of, processed_clip
from sqlalchemy import Engine
from sqlmodel import Session
from style_fakes import (
    PAGE,
    Web,
    fmt,
    offline_web,  # noqa: F401
    page,
    small_reference,  # noqa: F401
)
from style_recipe_fixtures import REFS, features

API = "/api/proedit/style-recipes"
CLIPS = "/api/proedit/clips"


class ReplyLLM:
    """An LLM that describes every recipe the same way."""

    def complete_json(self, system: str, user: str) -> str:
        return '{"description": "Calm talking head, few cuts."}'


def set_llm(client: TestClient, llm: object) -> None:
    client.app.state.llm = llm  # type: ignore[attr-defined]


def exported(name: str = "Night phonk", refs: list[Any] = REFS) -> dict[str, Any]:
    return {
        "format": "clipforge.style_recipe",
        "version": 1,
        "name": name,
        "description": "Fast cuts.",
        "reference_count": len(refs),
        "targets": aggregate(refs).model_dump(mode="json"),
    }


def imported(client: TestClient, refs: list[Any] = REFS) -> dict[str, Any]:
    response = client.post(f"{API}/import", json=exported(refs=refs))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_the_metrics_have_their_sliders(client: TestClient) -> None:
    body = client.get(f"{API}/metrics").json()

    assert [metric["key"] for metric in body] == [m.key for m in METRICS]
    cuts = body[0]
    assert cuts == {
        "key": "cuts_per_minute",
        "label": "Cuts",
        "unit": "/min",
        "group": "rhythm",
        "min": 0,
        "max": 120,
        "step": 1,
        "tolerance": 6,
    }


@pytest.mark.parametrize(
    ("llm", "described"),
    [(ReplyLLM(), "Calm talking head, few cuts."), (OfflineLLM(), None)],
)
def test_an_analysis_stores_targets_and_a_description(
    client: TestClient, web: Web, small: Path, llm: object, described: str | None
) -> None:
    set_llm(client, llm)
    web.pages[PAGE] = page(60, fmt("18", small, 240))
    recipe_id = client.post(
        API, json={"name": "Phonk", "urls": [PAGE], "rights_confirmed": True}
    ).json()["recipe"]["id"]

    body = client.post(f"{API}/{recipe_id}/analyze").json()

    (measured,) = body["recipe"]["features"]["references"].values()
    targets = StyleTargets.model_validate(body["targets"])
    assert targets == aggregate([measured])
    assert targets.metrics["cuts_per_minute"].count == 1
    assert body["recipe"]["description"] == (described or describe_rules(targets))
    assert client.get(f"{API}/{recipe_id}").json()["targets"] == body["targets"]


def test_a_recipe_is_edited_by_name_description_and_targets(
    client: TestClient,
) -> None:
    recipe_id = imported(client)["recipe"]["id"]
    targets = exported()["targets"]
    targets["metrics"]["cuts_per_minute"] = {"median": 60, "low": 50, "high": 70}

    response = client.patch(
        f"{API}/{recipe_id}",
        json={"name": " Faster ", "description": "Very fast.", "targets": targets},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recipe"]["name"] == "Faster"
    assert body["recipe"]["description"] == "Very fast."
    assert body["targets"]["metrics"]["cuts_per_minute"] == {
        "median": 60,
        "low": 50,
        "high": 70,
        "count": 0,
    }
    only_name = client.patch(f"{API}/{recipe_id}", json={"name": "Again"}).json()
    assert only_name["targets"] == body["targets"]


def test_bad_edits_are_refused(client: TestClient) -> None:
    recipe_id = imported(client)["recipe"]["id"]
    unknown = {"metrics": {"warp": {"median": 1, "low": 1, "high": 1}}}
    reversed_range = {"metrics": {"bpm": {"median": 100, "low": 120, "high": 140}}}

    assert_error(
        client.patch(f"{API}/{recipe_id}", json={"targets": unknown}),
        422,
        "validation_error",
    )
    assert_error(
        client.patch(f"{API}/{recipe_id}", json={"targets": reversed_range}),
        422,
        "validation_error",
    )
    assert_error(
        client.patch(f"{API}/{recipe_id}", json={"name": "  "}),
        422,
        "validation_error",
    )
    assert_error(client.patch(f"{API}/999", json={"name": "x"}), 404, "not_found")
    assert client.get(f"{API}/{recipe_id}").json()["recipe"]["name"] == "Night phonk"


def test_the_export_is_a_file_without_media_paths_or_links(
    client: TestClient, web: Web, small: Path, data_dir: Path
) -> None:
    set_llm(client, OfflineLLM())
    web.pages[PAGE] = page(60, fmt("18", small, 240))
    recipe_id = client.post(
        API, json={"name": "Night Phonk!", "urls": [PAGE], "rights_confirmed": True}
    ).json()["recipe"]["id"]
    client.post(f"{API}/{recipe_id}/analyze")

    response = client.get(f"{API}/{recipe_id}/export")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="night-phonk.style-recipe.json"'
    )
    body = response.json()
    assert set(body) == {
        "format",
        "version",
        "name",
        "description",
        "reference_count",
        "targets",
    }
    assert body["reference_count"] == 1
    assert body["targets"]["metrics"]
    for leak in (str(data_dir), ".mp4", "http", "references", "example"):
        assert leak not in response.text
    assert_error(client.get(f"{API}/999/export"), 404, "not_found")


def test_an_export_imports_as_a_new_recipe_without_references(
    client: TestClient,
) -> None:
    body = imported(client)

    assert body["recipe"]["name"] == "Night phonk"
    assert body["recipe"]["reference_count"] == 3
    assert body["references"] == []
    assert body["targets"] == exported()["targets"]
    again = client.get(f"{API}/{body['recipe']['id']}/export").json()
    assert again == exported()


def test_an_import_with_media_or_unknown_metrics_is_refused(
    client: TestClient,
) -> None:
    with_media = {**exported(), "media": "/tmp/ref.mp4"}
    unknown = exported()
    unknown["targets"]["metrics"]["warp"] = {"median": 1, "low": 1, "high": 1}

    assert_error(client.post(f"{API}/import", json=with_media), 422, "validation_error")
    assert_error(client.post(f"{API}/import", json=unknown), 422, "validation_error")
    assert client.get(API).json() == []


@pytest.fixture
def variant(api_engine: Engine, sample_mp4: Path) -> Processed:
    """A rendered clip with its video."""
    clip = processed_clip(api_engine, sample_mp4)
    output = clip_of(api_engine, clip.clip_id).output_path
    assert output is not None
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_bytes(sample_mp4.read_bytes())
    return clip


def plan_with(engine: Engine, clip_id: int, recipe_id: int | None) -> None:
    plan = ProEditPlan(
        id=1,
        clip_id=clip_id,
        preset="phonk_edit",
        intensity="pro",
        style_recipe_id=recipe_id,
        version=1,
        items=[],
        created_by="rule_director",
    )
    with Session(engine) as session:
        save_plan(session, plan)


def test_the_style_match_scores_the_clip_against_its_plans_recipe(
    client: TestClient,
    api_engine: Engine,
    variant: Processed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe_id = imported(client, [REFS[0]])["recipe"]["id"]
    plan_with(api_engine, variant.clip_id, recipe_id)
    measured = [REFS[0]]
    monkeypatch.setattr(match, "measure_features", lambda _path: measured[0])
    url = f"{CLIPS}/{variant.clip_id}/style-match"
    before = client.get(url)

    same = client.post(url)

    assert before.status_code == 200 and before.json() is None
    assert same.status_code == 200, same.text
    body = same.json()
    assert body["score"] == 100
    assert body["recipe_id"] == recipe_id and body["recipe_name"] == "Night phonk"
    assert {m["key"] for m in body["metrics"]} == set(aggregate([REFS[0]]).metrics)
    assert client.get(url).json() == body
    measured[0] = features(90.0, 0.4, 0.8, 70.0, "#000000")
    distant = client.post(url).json()
    assert distant["score"] < 100
    output = clip_of(api_engine, variant.clip_id).output_path
    assert output is not None
    os.utime(output, (1, 1))
    assert client.get(url).json() is None


def test_the_style_match_answers_404_and_409(
    client: TestClient, api_engine: Engine, variant: Processed
) -> None:
    url = f"{CLIPS}/{variant.clip_id}/style-match"
    recipe_id = imported(client)["recipe"]["id"]

    assert_error(client.post(f"{CLIPS}/999/style-match"), 404, "not_found")
    assert_error(client.post(url), 409, "conflict")
    assert_error(client.get(f"{url}?recipe_id=999"), 404, "not_found")
    output = clip_of(api_engine, variant.clip_id).output_path
    assert output is not None
    Path(output).unlink()
    assert_error(client.post(f"{url}?recipe_id={recipe_id}"), 409, "conflict")
