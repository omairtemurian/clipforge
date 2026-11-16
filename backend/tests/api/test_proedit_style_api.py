"""Tests of the /proedit/style-recipes endpoints (SPEC-v3 4.1, 4.2): the
rights confirmation, the link and duration limits, and the analysis that
deletes the media. Downloads run the real yt-dlp on canned pages
(style_fakes); the analysis measures the real features of the files."""

from pathlib import Path
from typing import Any

import pytest
from apihelpers import assert_error
from clipforge.proedit.rows import StyleRecipeRow, StyleReferenceRow
from clipforge.proedit.style import fetch
from clipforge.proedit.style.fetch import style_dir
from fastapi.testclient import TestClient
from proedit_run_fakes import OfflineLLM
from sqlalchemy import Engine
from sqlmodel import Session, select
from style_fakes import (
    BROKEN_PAGE,
    LONG_PAGE,
    PAGE,
    Web,
    fmt,
    offline_web,  # noqa: F401
    page,
    small_reference,  # noqa: F401
)

API = "/api/proedit/style-recipes"
OTHER = "https://www.youtube.com/watch?v=styleref09"


@pytest.fixture(autouse=True)
def offline_llm(client: TestClient) -> None:
    """Describe recipes by rules: the LLM of the app is offline."""
    client.app.state.llm = OfflineLLM()  # type: ignore[attr-defined]


def create(client: TestClient, urls: list[str], **body: Any) -> Any:
    fields = {"name": "Phonk", "urls": urls, "rights_confirmed": True, **body}
    return client.post(API, json=fields)


def test_the_terms_give_the_notice_and_the_limits(client: TestClient) -> None:
    response = client.get(f"{API}/terms")

    assert response.status_code == 200
    assert response.json() == {
        "notice": (
            "Downloading videos may break the site's terms; use only "
            "references you have the right to analyze."
        ),
        "max_links": 5,
        "max_seconds": 180,
        "max_height": 720,
    }


def test_a_recipe_is_stored_with_its_links_and_the_rights_time(
    client: TestClient, api_engine: Engine
) -> None:
    response = create(client, [PAGE, f" {OTHER} ", PAGE])

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recipe"]["name"] == "Phonk"
    assert body["recipe"]["reference_count"] == 0
    refs = [r["reference"] for r in body["references"]]
    assert [r["url"] for r in refs] == [PAGE, OTHER]
    assert all(r["rights_confirmed_at"] for r in refs)
    assert all(r["analyzed_at"] is None and r["deleted_at"] is None for r in refs)
    with Session(api_engine) as session:
        assert len(session.exec(select(StyleReferenceRow)).all()) == 2


def test_without_the_rights_confirmation_nothing_is_stored(
    client: TestClient, api_engine: Engine
) -> None:
    missing = client.post(API, json={"name": "Phonk", "urls": [PAGE]})
    unchecked = create(client, [PAGE], rights_confirmed=False)

    assert_error(missing, 422, "validation_error")
    assert_error(unchecked, 422, "validation_error")
    with Session(api_engine) as session:
        assert session.exec(select(StyleRecipeRow)).all() == []


def test_more_than_5_links_none_or_unsupported_links_are_422(
    client: TestClient,
) -> None:
    six = [f"https://www.youtube.com/watch?v=styleref1{n}" for n in range(6)]

    assert_error(create(client, six), 422, "validation_error")
    assert_error(create(client, []), 422, "validation_error")
    assert_error(create(client, ["/tmp/video.mp4"]), 422, "validation_error")
    assert_error(create(client, ["https://example.com/page"]), 422, "validation_error")
    assert_error(create(client, [PAGE], name=""), 422, "validation_error")
    assert client.get(API).json() == []


def test_a_recipe_is_listed_and_read_and_a_missing_one_is_404(
    client: TestClient,
) -> None:
    recipe_id = create(client, [PAGE]).json()["recipe"]["id"]

    assert [r["id"] for r in client.get(API).json()] == [recipe_id]
    assert client.get(f"{API}/{recipe_id}").json()["recipe"]["name"] == "Phonk"
    assert_error(client.get(f"{API}/999"), 404, "not_found")
    assert_error(client.post(f"{API}/999/analyze"), 404, "not_found")


def test_analyzing_stores_numbers_and_deletes_the_media(
    client: TestClient,
    data_dir: Path,
    web: Web,
    small: Path,
) -> None:
    web.pages[PAGE] = page(60, fmt("18", small, 240))
    recipe_id = create(client, [PAGE]).json()["recipe"]["id"]

    response = client.post(f"{API}/{recipe_id}/analyze")

    assert response.status_code == 200, response.text
    body = response.json()
    (result,) = body["references"]
    assert result["error"] is None
    assert result["reference"]["analyzed_at"] and result["reference"]["deleted_at"]
    assert body["recipe"]["reference_count"] == 1
    (measured,) = body["recipe"]["features"]["references"].values()
    assert set(measured) == {
        "video",
        "rhythm",
        "motion",
        "look",
        "glitches",
        "captions",
        "audio",
        "structure",
    }
    assert measured["video"]["fps"] == 30
    assert set(measured["video"]) >= {"duration", "cuts", "motion", "color", "flashes"}
    assert 0.9 <= measured["video"]["duration"] <= 1.1
    ref_id = result["reference"]["id"]
    assert not style_dir(ref_id).exists()
    assert str(data_dir) not in response.text


def test_a_reference_over_the_limits_carries_its_reason_and_leaves_no_media(
    client: TestClient,
    web: Web,
    small: Path,
) -> None:
    web.pages[PAGE] = page(60, fmt("18", small, 240))
    web.pages[LONG_PAGE] = page(600, fmt("18", small, 240))
    recipe_id = create(client, [PAGE, LONG_PAGE, BROKEN_PAGE]).json()["recipe"]["id"]

    body = client.post(f"{API}/{recipe_id}/analyze").json()

    first, long, broken = body["references"]
    assert first["error"] is None
    assert "3 min" in long["error"]
    assert "Video unavailable" in broken["error"]
    assert body["recipe"]["reference_count"] == 1
    for result in (first, long, broken):
        assert result["reference"]["deleted_at"]
        assert not style_dir(result["reference"]["id"]).exists()
    assert long["reference"]["analyzed_at"] is None


def test_only_the_references_not_analyzed_yet_are_analyzed_again(
    client: TestClient,
    web: Web,
    small: Path,
) -> None:
    web.pages[PAGE] = page(60, fmt("18", small, 240))
    recipe_id = create(client, [PAGE]).json()["recipe"]["id"]
    first = client.post(f"{API}/{recipe_id}/analyze").json()
    downloads = len(web.params)

    again = client.post(f"{API}/{recipe_id}/analyze").json()

    assert len(web.params) == downloads
    assert again["recipe"]["features"] == first["recipe"]["features"]


def test_a_recipe_being_analyzed_answers_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = create(client, [PAGE]).json()
    ref_id = body["references"][0]["reference"]["id"]
    monkeypatch.setattr(fetch, "_active", {ref_id})

    response = client.post(f"{API}/{body['recipe']['id']}/analyze")

    assert_error(response, 409, "conflict")
