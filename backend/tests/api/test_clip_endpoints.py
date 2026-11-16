"""Tests of the clip endpoints: list, get, patch and regenerate-text."""

import json
from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge.api.app import create_app
from clipforge.db import ClipRow
from clipforge.llm_http import LLMError
from clipforge.models import Clip
from clipforge.pipeline.export import metadata_path, srt_path
from clipforge.pipeline.render import clip_output
from clipforge.preview import previews_dir
from fakes import FakeLLMClient
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session

NEW_TEXT = {
    "title": "Yoga told me to listen",
    "description": "A body with one question.",
    "hashtags": ["yoga", "standup", "comedy"],
}


def clip_ids(client: TestClient, url: str) -> list[int]:
    """GET url, a list of clips, and return their ids in order."""
    response = client.get(url)
    assert response.status_code == 200
    return [Clip.model_validate(item).id for item in response.json()]


def stored(engine: Engine, clip_id: int) -> Clip:
    """Return clip clip_id as the database has it."""
    with Session(engine) as session:
        return session.get_one(ClipRow, clip_id).to_model()


class FailingLLM:
    """An LLM that cannot be reached."""

    def complete_json(self, system: str, user: str) -> str:
        raise LLMError("POST https://llm.test/chat/completions failed: refused")


def test_clips_are_listed_sorted_and_filtered(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    other = add_project(api_engine)
    low = add_clip(api_engine, project_id, "candidate", 55, "Smart fridge", end=40.0)
    best = add_clip(api_engine, project_id, "rendered", 91, "Yoga", hashtags=["Gym"])
    mid = add_clip(api_engine, project_id, "candidate", 70, "Cheese", start=11.0)
    add_clip(api_engine, other, "candidate", 99, "Elsewhere")
    url = f"/api/projects/{project_id}/clips"

    assert clip_ids(client, url) == [best, mid, low]
    assert clip_ids(client, f"{url}?sort=duration") == [mid, best, low]
    assert clip_ids(client, f"{url}?min_score=70") == [best, mid]
    assert clip_ids(client, f"{url}?q=FRIDGE") == [low]
    assert clip_ids(client, f"{url}?q=gym") == [best]
    assert clip_ids(client, f"{url}?q=%20%20") == [best, mid, low]
    assert clip_ids(client, f"{url}?sort=duration&min_score=60&q=e") == [mid, best]
    assert clip_ids(client, f"/api/projects/{other}/clips?min_score=99") != []


def test_listing_clips_needs_a_project_and_valid_filters(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    url = f"/api/projects/{project_id}/clips"

    assert client.get(url).json() == []
    assert_error(client.get("/api/projects/42/clips"), 404, "not_found")
    assert "sort" in assert_error(
        client.get(f"{url}?sort=views"), 422, "validation_error"
    )
    assert_error(client.get(f"{url}?min_score=100"), 422, "validation_error")
    assert_error(client.get(f"{url}?min_score=-1"), 422, "validation_error")


def test_a_clip_is_returned(client: TestClient, api_engine: Engine) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80, "Pizza")

    response = client.get(f"/api/clips/{clip_id}")

    assert response.status_code == 200
    assert Clip.model_validate(response.json()) == stored(api_engine, clip_id)
    assert_error(client.get("/api/clips/42"), 404, "not_found")
    assert_error(client.get("/api/clips/pizza"), 422, "validation_error")


def test_patch_changes_only_the_fields_it_sets(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80, "Pizza")
    word = {"text": "brother!", "start": 10.4, "end": 10.9, "speaker": "S0", "prob": 1}
    body = {
        "start": 9.5,
        "end": 13.0,
        "title": "New title",
        "hook_text": "Wait for it",
        "hashtags": ["one", "two"],
        "layout": "split",
        "caption_template": "neon",
        "caption_overrides": [word],
        "cut_ranges": [[12.0, 12.4], [10.0, 10.3]],
        "description": None,
    }

    response = client.patch(f"/api/clips/{clip_id}", json=body)

    assert response.status_code == 200
    clip = stored(api_engine, clip_id)
    assert Clip.model_validate(response.json()) == clip
    assert (clip.start, clip.end, clip.title, clip.hook_text) == (
        9.5,
        13.0,
        "New title",
        "Wait for it",
    )
    assert (clip.hashtags, clip.layout, clip.caption_template) == (
        ["one", "two"],
        "split",
        "neon",
    )
    assert clip.caption_overrides[0].text == "brother!"
    assert clip.cut_ranges == [(10.0, 10.3), (12.0, 12.4)]
    assert (clip.description, clip.status, clip.scores.overall) == ("", "candidate", 80)


def test_patch_replaces_the_caption_style_crop_offset_and_auto_cut(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80, "Pizza")
    assert stored(api_engine, clip_id).caption_style.model_dump(exclude_none=True) == {}
    style = {"size": 90, "primary_color": "#FFAA00", "position": "middle"}

    body = {"caption_style": style, "crop_offset": -0.25, "auto_cut": True}
    response = client.patch(f"/api/clips/{clip_id}", json=body)

    assert response.status_code == 200
    clip = stored(api_engine, clip_id)
    assert Clip.model_validate(response.json()) == clip
    assert clip.caption_style.model_dump(exclude_none=True) == style
    assert (clip.crop_offset, clip.auto_cut) == (-0.25, True)

    client.patch(f"/api/clips/{clip_id}", json={"caption_style": {"emoji": True}})
    clip = stored(api_engine, clip_id)
    assert clip.caption_style.model_dump(exclude_none=True) == {"emoji": True}
    assert (clip.crop_offset, clip.auto_cut) == (-0.25, True)


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ({"end": 10.0}, "end (10) must be after start (10)"),
        ({"start": 13.0}, "end (12.5) must be after start (13)"),
        ({"end": 61.0}, "after the end of the video (60)"),
        ({"cut_ranges": [[9.0, 10.5]]}, "cut range [9, 10.5] is not a range inside"),
        ({"cut_ranges": [[11.0, 13.0]]}, "is not a range inside the clip [10, 12.5]"),
        ({"cut_ranges": [[11.0, 11.0]]}, "cut range [11, 11] is not a range"),
        ({"cut_ranges": [[10.0, 11.5], [11.0, 12.5]]}, "leave nothing of the clip"),
        ({"caption_template": "fancy"}, "unknown caption template 'fancy'"),
        (
            {"caption_style": {"font": "Comic Sans MS"}},
            "caption font 'Comic Sans MS' is not a bundled font",
        ),
        ({"end": 20.0, "cut_ranges": [[19.0, 21.0]]}, "[19, 21] is not a range"),
    ],
)
def test_patch_rejects_an_invalid_clip_and_changes_nothing(
    client: TestClient, api_engine: Engine, body: dict[str, object], problem: str
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80, "Pizza")
    before = stored(api_engine, clip_id)

    response = client.patch(f"/api/clips/{clip_id}", json=body)

    assert problem in assert_error(response, 422, "validation_error")
    assert stored(api_engine, clip_id) == before


@pytest.mark.parametrize(
    "body",
    [
        {"status": "rendered"},
        {"title": "x" * 71},
        {"hashtags": ["#yoga"]},
        {"layout": "zoom"},
        {"start": -1},
        {"cut_ranges": [[1.0]]},
        {"crop_offset": 1.5},
        {"caption_style": {"size": 10}},
        {"caption_style": {"primary_color": "red"}},
        {"caption_style": {"position": "upper_third"}},
        {"caption_style": {"bold": True}},
        {"caption_style": {"max_lines": 3}},
        {"caption_style": {"animation": "spin"}},
    ],
)
def test_patch_validates_its_body(
    client: TestClient, api_engine: Engine, body: dict[str, object]
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80, "Pizza")

    assert_error(
        client.patch(f"/api/clips/{clip_id}", json=body), 422, "validation_error"
    )


def test_patch_needs_a_clip_that_is_not_rendering(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "rendering", 80, "Pizza")

    assert_error(client.patch("/api/clips/42", json={}), 404, "not_found")
    response = client.patch(f"/api/clips/{clip_id}", json={"title": "Later"})
    assert "rendering" in assert_error(response, 409, "conflict")
    assert stored(api_engine, clip_id).title == "Pizza"


def test_regenerate_text_saves_the_llm_text_of_the_clips_words(
    data_dir: Path, sample_mp4: Path
) -> None:
    llm = FakeLLMClient('{"title": "' + "x" * 80 + '"}', json.dumps(NEW_TEXT))
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
        project_id = add_project(engine)
        add_work(engine, project_id, sample_mp4)
        clip_id = add_clip(engine, project_id, "candidate", 80, "Pizza")

        response = client.post(f"/api/clips/{clip_id}/regenerate-text")

    assert response.status_code == 200
    clip = stored(engine, clip_id)
    assert Clip.model_validate(response.json()) == clip
    assert (clip.title, clip.description, clip.hashtags) == (
        NEW_TEXT["title"],
        NEW_TEXT["description"],
        NEW_TEXT["hashtags"],
    )
    assert (clip.hook_text, clip.start, clip.end) == ("He ate it all", 10.0, 12.5)
    (system, first), (_, retry) = llm.calls
    assert '"hashtags"' in system and "maxLength" in system
    assert "What is said in the clip:\nsaid, why are we on\n\n" in first
    assert "Current title: Pizza" in first
    assert "title: String should have at most 70 characters" in retry


def test_regenerate_text_reports_llm_failures(data_dir: Path, sample_mp4: Path) -> None:
    invalid = FakeLLMClient("not json", repeat_last=True)
    for llm, message in ((invalid, "no valid text"), (FailingLLM(), "refused")):
        with TestClient(create_app(run_worker=False, llm=llm)) as client:
            engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
            project_id = add_project(engine)
            add_work(engine, project_id, sample_mp4)
            clip_id = add_clip(engine, project_id, "candidate", 80, "Pizza")

            response = client.post(f"/api/clips/{clip_id}/regenerate-text")

        assert message in assert_error(response, 502, "llm_error")
        assert stored(engine, clip_id).title == "Pizza"
    assert len(invalid.calls) == 3


def test_regenerate_text_needs_a_clip_with_a_transcript(
    data_dir: Path, sample_mp4: Path
) -> None:
    with TestClient(create_app(run_worker=False, llm=FakeLLMClient())) as client:
        engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
        project_id = add_project(engine)
        clip_id = add_clip(engine, project_id, "candidate", 80, "Pizza")

        assert_error(client.post("/api/clips/42/regenerate-text"), 404, "not_found")
        no_job = client.post(f"/api/clips/{clip_id}/regenerate-text")
        assert "no process job" in assert_error(no_job, 409, "conflict")
        work = add_work(engine, project_id, sample_mp4)
        (work / "transcript.json").unlink()
        no_words = client.post(f"/api/clips/{clip_id}/regenerate-text")
        assert "transcript.json" in assert_error(no_words, 409, "conflict")
        bad_id = client.post("/api/clips/x/regenerate-text")
        assert_error(bad_id, 422, "validation_error")


def test_a_deleted_clip_loses_its_row_and_files(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    gone = add_clip(api_engine, project_id, "rendered", 80, "Pizza")
    kept = add_clip(api_engine, project_id, "rendered", 70, "Yoga")
    video = clip_output(project_id, gone)
    kept_video = clip_output(project_id, kept)
    previews = previews_dir(project_id)
    previews.mkdir(parents=True)
    files = [video, srt_path(video), metadata_path(video), previews / f"{gone}-ab.mp4"]
    files += [kept_video, previews / f"{kept}-cd.mp4"]
    for path in files:
        path.write_bytes(b"x")

    response = client.delete(f"/api/clips/{gone}")

    assert (response.status_code, response.content) == (204, b"")
    assert clip_ids(client, f"/api/projects/{project_id}/clips") == [kept]
    assert [path.exists() for path in files] == [False] * 4 + [True] * 2
    assert_error(client.delete(f"/api/clips/{gone}"), 404, "not_found")
    assert_error(client.delete("/api/clips/x"), 422, "validation_error")


def test_a_rendering_clip_cannot_be_deleted(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "rendering", 80)

    assert "is rendering" in assert_error(
        client.delete(f"/api/clips/{clip_id}"), 409, "conflict"
    )
    assert stored(api_engine, clip_id).id == clip_id
