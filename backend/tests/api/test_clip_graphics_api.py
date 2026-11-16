"""Tests of the auto headline and motion graphics through the API (SPEC-v2
3.5): a headline from given text or the LLM (mocked), regenerated without
losing edits and removed; motion graphics the LLM picks, placed on their
words in the project's brand style, limited by the text track's room and
removed; each a version that undo takes back; errors answer 404, 409, 422
or 502."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from apihelpers import assert_error
from builders import track_item
from clipforge.api.app import create_app
from clipforge.brand_style import DEFAULT_COLOR, DEFAULT_FONT
from clipforge.db import BrandTemplateRow, ClipRow, ProjectRow
from clipforge.llm_http import LLMError
from clipforge.models import Clip, ProcessingSettings, TextProps
from clipforge.pipeline.headline import HEADLINE_ID
from fakes import FakeLLMClient
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session

FRIDGE = {"kind": "phrase", "text": "Smart fridge", "quote": "smart fridges"}
NIGHT = {
    "kind": "date",
    "text": "Every night",
    "label": "a full report",
    "quote": "every night",
}
TOASTER = {"kind": "phrase", "text": "Toaster", "quote": "my toaster"}


class FailingLLM:
    """An LLM that cannot be reached."""

    def complete_json(self, system: str, user: str) -> str:
        raise LLMError("POST https://llm.test/chat/completions failed: refused")


def stored(engine: Engine, clip_id: int) -> Clip:
    """Return clip clip_id as the database has it."""
    with Session(engine) as session:
        return session.get_one(ClipRow, clip_id).to_model()


def branded_project(engine: Engine) -> int:
    """Add a project whose settings pick a brand template in Anton and
    #00AA55; return its id."""
    project_id = add_project(engine)
    with Session(engine) as session:
        brand = BrandTemplateRow(
            name="Acme",
            logo_path="/brand/logo.png",
            logo_position="br",
            logo_opacity=0.8,
            font="Anton",
            primary_color="#00AA55",
        )
        session.add(brand)
        session.flush()
        project = session.get_one(ProjectRow, project_id)
        project.settings = ProcessingSettings(brand_template_id=brand.id)
        session.add(project)
        session.commit()
    return project_id


def props(clip: Clip, item_id: str) -> TextProps:
    """Return the props of clip's text item item_id."""
    [item] = [item for item in clip.tracks.text if item.id == item_id]
    return TextProps.model_validate(item.props)


@pytest.fixture
def llm() -> FakeLLMClient:
    """An LLM whose replies are given by the test (its parametrize)."""
    return FakeLLMClient(json.dumps({"text": "Smart fridge snitches"}))


@pytest.fixture
def llm_client(
    data_dir: Path, llm: FakeLLMClient
) -> Iterator[tuple[TestClient, Engine]]:
    """A client of an app that asks llm, and its engine."""
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        yield client, client.app.state.engine  # type: ignore[attr-defined]


def test_a_given_headline_is_drawn_in_the_brand_style_and_undone(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, branded_project(api_engine), "candidate", 80)
    url = f"/api/clips/{clip_id}/headline"

    response = client.post(url, json={"text": "  Wait for  it "})

    assert response.status_code == 200
    clip = stored(api_engine, clip_id)
    assert Clip.model_validate(response.json()) == clip
    assert clip.hook_text == "Wait for  it"
    head = props(clip, HEADLINE_ID)
    assert (head.text, head.font, head.box) == ("Wait for it", "Anton", "#00AA55")
    history = client.get(f"/api/clips/{clip_id}/versions").json()
    assert sorted(history["versions"][-1]["fields"]) == ["hook_text", "tracks"]
    undone = client.post(f"/api/clips/{clip_id}/undo").json()
    assert (undone["hook_text"], undone["tracks"]["text"]) == ("He ate it all", [])


def test_the_llm_writes_the_headline_and_an_edited_one_keeps_its_style(
    llm_client: tuple[TestClient, Engine], llm: FakeLLMClient, sample_mp4: Path
) -> None:
    client, engine = llm_client
    project_id = add_project(engine)
    add_work(engine, project_id, sample_mp4)
    clip_id = add_clip(engine, project_id, "candidate", 80, "Fridge")
    url = f"/api/clips/{clip_id}/headline"
    first = Clip.model_validate(client.post(url, json={"text": "Old"}).json())
    [item] = first.tracks.text
    edited = item.model_copy(update={"end": 1.5, "props": item.props | {"y": 0.3}})
    tracks = first.tracks.model_copy(update={"text": [edited]})
    put = client.put(f"/api/clips/{clip_id}/tracks", json=tracks.model_dump())
    assert put.status_code == 200

    response = client.post(url, json={"text": None})

    assert response.status_code == 200
    clip = stored(engine, clip_id)
    assert clip.hook_text == "Smart fridge snitches"
    [again] = clip.tracks.text
    head = props(clip, HEADLINE_ID)
    assert (again.end, head.y, head.text) == (1.5, 0.3, "Smart fridge\nsnitches")
    assert (head.font, head.box) == (DEFAULT_FONT, DEFAULT_COLOR)
    [(system, user)] = llm.calls
    assert "headline" in system
    assert "said, why are we on\n\nTitle: Fridge" in user


def test_removing_the_headline_clears_its_text_and_item(
    client: TestClient, api_engine: Engine
) -> None:
    other = track_item("t1", "text", 0.0, 1.0, props={"text": "Note"})
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    url = f"/api/clips/{clip_id}/headline"
    client.post(url, json={"text": "Hi"})
    with Session(api_engine) as session:
        row = session.get_one(ClipRow, clip_id)
        clip = row.to_model()
        row.tracks = clip.tracks.model_copy(update={"text": [*clip.tracks.text, other]})
        session.add(row)
        session.commit()

    response = client.delete(url)

    assert response.status_code == 200
    clip = stored(api_engine, clip_id)
    assert clip.hook_text == ""
    assert [item.id for item in clip.tracks.text] == ["t1"]
    assert client.delete(url).status_code == 200


@pytest.mark.parametrize(
    "llm",
    [
        FakeLLMClient(
            json.dumps({"items": [FRIDGE, TOASTER]}),
            json.dumps({"items": [NIGHT, FRIDGE]}),
        )
    ],
)
def test_motion_graphics_go_on_their_words_in_the_brand_style(
    llm_client: tuple[TestClient, Engine], llm: FakeLLMClient, sample_mp4: Path
) -> None:
    client, engine = llm_client
    project_id = branded_project(engine)
    add_work(engine, project_id, sample_mp4)
    clip_id = add_clip(engine, project_id, "candidate", 80, start=16.9, end=33.0)
    url = f"/api/clips/{clip_id}/motion-graphics"

    response = client.post(url, json={"max_items": 2})

    assert response.status_code == 200
    clip = stored(engine, clip_id)
    items = clip.tracks.text
    assert [item.id for item in items] == ["mg-0", "mg-1"]
    assert [item.start for item in items] == pytest.approx([1.94, 9.41], abs=1e-6)
    assert [item.end for item in items] == pytest.approx([3.94, 11.41], abs=1e-6)
    fridge, night = props(clip, "mg-0"), props(clip, "mg-1")
    assert (fridge.text, fridge.font) == ("Smart fridge", "Anton")
    assert fridge.box == "#00AA55"
    assert (night.text, night.color) == ("Every night\na full report", "#00AA55")
    (system, _), (_, retry) = llm.calls
    assert "at most 2" in system
    assert "'my toaster' is not said word for word" in retry
    history = client.get(f"/api/clips/{clip_id}/versions").json()
    assert history["versions"][-1]["fields"] == ["tracks"]

    removed = client.delete(url)

    assert removed.status_code == 200 and stored(engine, clip_id).tracks.text == []
    assert len(client.post(f"/api/clips/{clip_id}/undo").json()["tracks"]["text"]) == 2


@pytest.mark.parametrize(
    "llm", [FakeLLMClient(json.dumps({"items": [FRIDGE, NIGHT]}), repeat_last=True)]
)
def test_the_text_tracks_other_items_limit_the_motion_graphics(
    llm_client: tuple[TestClient, Engine], llm: FakeLLMClient, sample_mp4: Path
) -> None:
    client, engine = llm_client
    project_id = add_project(engine)
    add_work(engine, project_id, sample_mp4)
    others = [
        track_item(f"t{k}", "text", 0.0, 1.0, props={"text": f"n{k}"}) for k in range(4)
    ]
    clip_id = add_clip(engine, project_id, "candidate", 80, start=16.9, end=33.0)
    with Session(engine) as session:
        row = session.get_one(ClipRow, clip_id)
        row.tracks = row.to_model().tracks.model_copy(update={"text": others})
        session.add(row)
        session.commit()
    url = f"/api/clips/{clip_id}/motion-graphics"

    response = client.post(url, json={"max_items": 3})
    again = client.post(url, json={})

    assert response.status_code == again.status_code == 200
    ids = [item.id for item in stored(engine, clip_id).tracks.text]
    assert ids == ["t0", "t1", "t2", "t3", "mg-0"]
    assert "at most 1" in llm.calls[0][0]
    with Session(engine) as session:
        row = session.get_one(ClipRow, clip_id)
        extra = track_item("t4", "text", 0.0, 1.0, props={"text": "n4"})
        row.tracks = row.to_model().tracks.model_copy(update={"text": [*others, extra]})
        session.add(row)
        session.commit()
    calls = len(llm.calls)

    full = client.post(url, json={})

    assert "text track is full" in assert_error(full, 422, "validation_error")
    assert len(llm.calls) == calls


def test_graphics_errors(client: TestClient, api_engine: Engine) -> None:
    project_id = add_project(api_engine)
    clip_id = add_clip(api_engine, project_id, "candidate", 80)
    rendering = add_clip(api_engine, project_id, "rendering", 80)

    for method, path, body in [
        ("POST", "headline", {"text": "hi"}),
        ("DELETE", "headline", None),
        ("POST", "motion-graphics", {}),
        ("DELETE", "motion-graphics", None),
    ]:
        missing = client.request(method, f"/api/clips/999/{path}", json=body)
        assert_error(missing, 404, "not_found")
    assert "rendering" in assert_error(
        client.post(f"/api/clips/{rendering}/headline", json={"text": "hi"}),
        409,
        "conflict",
    )
    assert_error(
        client.post(f"/api/clips/{clip_id}/headline", json={"text": None}),
        409,
        "conflict",
    )
    assert_error(
        client.post(f"/api/clips/{clip_id}/motion-graphics", json={}), 409, "conflict"
    )
    for body in [{"text": "x" * 61}, {"text": "  "}]:
        bad = client.post(f"/api/clips/{clip_id}/headline", json=body)
        assert_error(bad, 422, "validation_error")
    for body in [{"max_items": 0}, {"max_items": 6}]:
        bad = client.post(f"/api/clips/{clip_id}/motion-graphics", json=body)
        assert_error(bad, 422, "validation_error")
    assert stored(api_engine, clip_id).tracks.text == []


@pytest.mark.parametrize("llm", [FakeLLMClient("not json", repeat_last=True)])
def test_no_valid_reply_is_502(
    llm_client: tuple[TestClient, Engine], sample_mp4: Path
) -> None:
    client, engine = llm_client
    project_id = add_project(engine)
    add_work(engine, project_id, sample_mp4)
    clip_id = add_clip(engine, project_id, "candidate", 80)

    headline = client.post(f"/api/clips/{clip_id}/headline", json={"text": None})
    graphics = client.post(f"/api/clips/{clip_id}/motion-graphics", json={})

    assert "no valid headline" in assert_error(headline, 502, "llm_error")
    assert "no valid motion graphics" in assert_error(graphics, 502, "llm_error")
    assert stored(engine, clip_id).tracks.text == []


def test_an_unreachable_llm_is_502(data_dir: Path, sample_mp4: Path) -> None:
    with TestClient(create_app(run_worker=False, llm=FailingLLM())) as client:
        engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
        project_id = add_project(engine)
        add_work(engine, project_id, sample_mp4)
        clip_id = add_clip(engine, project_id, "candidate", 80)

        response = client.post(f"/api/clips/{clip_id}/motion-graphics", json={})

    assert "refused" in assert_error(response, 502, "llm_error")
