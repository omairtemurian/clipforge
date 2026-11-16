"""Tests of POST /clips/{id}/quick-post: a clip posted to the default
accounts in one call (rendered first when needed, AI text when none is
given), human only, and refused as a whole when a post fails the checks."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from apihelpers import assert_error
from clipforge import config, posts
from clipforge.api import quick_post
from clipforge.api.app import create_app
from clipforge.db import ClipRow
from clipforge.models import Clip
from clipforge.oauth_tokens import Token
from clipforge.publishers import registry
from clipforge.token_store import TokenStore
from fakes import FIXTURES, FakeLLMClient
from fastapi.testclient import TestClient
from post_api_fakes import AGENT, rendered_clip
from seed import add_clip, add_project, add_work
from social_fakes import (
    ACCESS,
    CLIENT,
    VIDEOS_URL,
    ExamplePublisher,
    add_account,
    clip_of,
    set_rights,
    write_video,
)
from sqlalchemy import Engine
from sqlmodel import Session

COPY = json.loads((FIXTURES / "post_copy" / "replies.json").read_text())["first"]
TEXT = {"title": "Pizza night", "caption": "Slices.", "privacy": "SELF_ONLY"}
YOUTUBE = TEXT | {"privacy": "public"}


@pytest.fixture(autouse=True)
def platforms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ExamplePublisher the publisher of TikTok and YouTube."""
    entry = registry.PublisherEntry(
        factory=lambda: ExamplePublisher(CLIENT), settings_keys=("EXAMPLE",)
    )
    for platform in ("tiktok", "youtube"):
        monkeypatch.setitem(registry.ENTRIES, platform, entry)


@pytest.fixture
def uploads(respx_mock: respx.MockRouter) -> respx.Route:
    """The example API's video upload, which accepts every post."""
    return respx_mock.post(VIDEOS_URL).mock(
        return_value=httpx.Response(201, json={"id": "v1", "link": "https://ex/v1"})
    )


def connect(engine: Engine, external_id: str, platform: str, **kw: Any) -> int:
    """Add an account with a token and return its id."""
    account_id = add_account(engine, external_id, platform, **kw)  # type: ignore[arg-type]
    TokenStore.from_settings().save(f"ref-{external_id}", Token(access_token=ACCESS))
    return account_id


def post(client: TestClient, clip_id: int, **body: Any) -> httpx.Response:
    return client.post(f"/api/clips/{clip_id}/quick-post", json=body)


def test_posts_to_the_default_account_of_each_platform(
    client: TestClient, api_engine: Engine, uploads: respx.Route
) -> None:
    clip_id = rendered_clip(api_engine)
    main = connect(api_engine, "main", "tiktok", default=True)
    connect(api_engine, "side", "tiktok")
    channel = connect(api_engine, "chan", "youtube", default=True)
    texts = {"tiktok": TEXT, "youtube": YOUTUBE}

    response = post(client, clip_id, platforms=["tiktok", "youtube"], texts=texts)

    assert response.status_code == 201
    assert [p["account_id"] for p in response.json()] == [main, channel]
    stored = posts.list_posts(api_engine, clip_id=clip_id)
    assert [(p.status, p.url) for p in stored] == [("published", "https://ex/v1")] * 2
    assert uploads.call_count == 2


def test_a_named_account_replaces_the_platforms_default(
    client: TestClient, api_engine: Engine, uploads: respx.Route
) -> None:
    clip_id = rendered_clip(api_engine)
    connect(api_engine, "main", "tiktok", default=True)
    side = connect(api_engine, "side", "tiktok")

    response = post(client, clip_id, account_ids=[side], texts={"tiktok": TEXT})

    assert [p["account_id"] for p in response.json()] == [side]
    assert uploads.call_count == 1


def test_a_platform_without_a_default_account_is_refused(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = rendered_clip(api_engine)
    connect(api_engine, "side", "tiktok")

    response = post(client, clip_id, platforms=["tiktok"], texts={"tiktok": TEXT})

    assert_error(response, 409, "no_default_account")
    assert posts.list_posts(api_engine) == []


def test_there_must_be_something_to_post_to(
    client: TestClient, api_engine: Engine
) -> None:
    assert_error(post(client, rendered_clip(api_engine)), 422, "validation_error")


def test_api_keys_may_not_quick_post(client: TestClient, api_engine: Engine) -> None:
    clip_id = rendered_clip(api_engine)
    connect(api_engine, "main", "tiktok", default=True)

    response = client.post(
        f"/api/clips/{clip_id}/quick-post",
        json={"platforms": ["tiktok"], "texts": {"tiktok": TEXT}},
        headers=AGENT,
    )

    assert_error(response, 403, "human_only")
    assert posts.list_posts(api_engine) == []


def test_a_clip_without_a_video_is_rendered_first(
    client: TestClient,
    api_engine: Engine,
    uploads: respx.Route,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = add_project(api_engine)
    set_rights(api_engine, project_id, "own")
    clip_id = add_clip(api_engine, project_id, "candidate", 70, "Raw")
    add_work(api_engine, project_id, FIXTURES / "sample.mp4")
    connect(api_engine, "main", "tiktok", default=True)
    renders: list[int] = []

    def fake_render(engine: Engine, clip: int, work: Path) -> Clip:
        renders.append(clip)
        with Session(engine) as session:
            row = session.get_one(ClipRow, clip)
            path = write_video(Path(f"{work}/out.mp4"))
            row.status, row.output_path = "rendered", str(path)
            session.add(row)
            session.commit()
        return clip_of(engine, clip)

    monkeypatch.setattr(quick_post, "render_clip_row", fake_render)

    response = post(client, clip_id, platforms=["tiktok"], texts={"tiktok": TEXT})

    assert response.status_code == 201
    assert renders == [clip_id]
    assert clip_of(api_engine, clip_id).status == "rendered"
    assert posts.list_posts(api_engine)[0].status == "published"


def test_a_failed_render_posts_nothing(
    client: TestClient, api_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = add_project(api_engine)
    set_rights(api_engine, project_id, "own")
    clip_id = add_clip(api_engine, project_id, "candidate", 70, "Raw")
    add_work(api_engine, project_id, FIXTURES / "sample.mp4")
    connect(api_engine, "main", "tiktok", default=True)
    monkeypatch.setattr(
        quick_post, "render_clip_row", lambda *_: clip_of(api_engine, clip_id)
    )

    response = post(client, clip_id, platforms=["tiktok"], texts={"tiktok": TEXT})

    assert_error(response, 500, "render_failed")
    assert posts.list_posts(api_engine) == []


def test_a_clip_that_is_rendering_is_not_rendered_again(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    set_rights(api_engine, project_id, "own")
    clip_id = add_clip(api_engine, project_id, "rendering", 70, "Busy")
    connect(api_engine, "main", "tiktok", default=True)

    response = post(client, clip_id, platforms=["tiktok"], texts={"tiktok": TEXT})

    assert_error(response, 409, "conflict")


def test_one_refused_post_queues_none(client: TestClient, api_engine: Engine) -> None:
    clip_id = rendered_clip(api_engine)
    connect(api_engine, "main", "tiktok", default=True)
    connect(api_engine, "chan", "youtube", default=True)
    texts = {"tiktok": {"caption": "No privacy chosen"}, "youtube": YOUTUBE}

    response = post(client, clip_id, platforms=["youtube", "tiktok"], texts=texts)

    assert "privacy" in assert_error(response, 409, "post_not_ready")
    assert posts.list_posts(api_engine) == []


def test_posting_needs_source_rights(client: TestClient, api_engine: Engine) -> None:
    clip_id = rendered_clip(api_engine)
    set_rights(api_engine, clip_of(api_engine, clip_id).project_id, None)
    connect(api_engine, "main", "tiktok", default=True)

    response = post(client, clip_id, platforms=["tiktok"], texts={"tiktok": TEXT})

    assert_error(response, 409, "source_rights_missing")
    assert posts.list_posts(api_engine) == []


@pytest.fixture
def ai_client(data_dir: Path) -> Iterator[TestClient]:
    """A client of an app whose LLM answers the post copy."""
    llm = FakeLLMClient(json.dumps(COPY), repeat_last=True)
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        yield client


def test_a_missing_text_is_written_by_the_ai(
    ai_client: TestClient, uploads: respx.Route
) -> None:
    engine: Engine = ai_client.app.state.engine  # type: ignore[attr-defined]
    clip_id = rendered_clip(engine)
    add_work(engine, clip_of(engine, clip_id).project_id, FIXTURES / "sample.mp4")
    connect(engine, "chan", "youtube", default=True)

    response = post(ai_client, clip_id, platforms=["youtube"])

    assert response.status_code == 201
    (stored,) = posts.list_posts(engine, clip_id=clip_id)
    assert stored.payload["title"] == COPY["title"]
    assert stored.status == "published"


def test_the_ai_text_carries_the_always_included_hashtags(
    ai_client: TestClient, uploads: respx.Route
) -> None:
    engine: Engine = ai_client.app.state.engine  # type: ignore[attr-defined]
    clip_id = rendered_clip(engine)
    add_work(engine, clip_of(engine, clip_id).project_id, FIXTURES / "sample.mp4")
    connect(engine, "chan", "youtube", default=True, always_hashtags=["SideChannel"])
    config.settings = config.Settings(
        data_dir=config.settings.data_dir, always_hashtags=["MyBrand"]
    )

    response = post(ai_client, clip_id, platforms=["youtube"])

    assert response.status_code == 201
    (stored,) = posts.list_posts(engine, clip_id=clip_id)
    assert stored.payload["tags"][:2] == ["MyBrand", "SideChannel"]
    assert stored.payload["description"].endswith(
        "#MyBrand #SideChannel #yoga #standup #comedy #FunnyMoments"
    )
