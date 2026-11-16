"""Tests for queuing and publishing posts now through the API: the checks
that keep a post from going out (rights, campaign permission, render,
platform choices) and the upload right after publish now (made-up
platform, respx)."""

import httpx
import pytest
import respx
from apihelpers import assert_error
from campaign_api import add, in_campaign
from clipforge import posts
from clipforge.oauth_tokens import Token
from clipforge.token_store import TokenStore
from fastapi.testclient import TestClient
from post_api_fakes import LATER, accounts, make_draft, rendered_clip
from seed import add_clip
from social_fakes import ACCESS, VIDEOS_URL, clip_of, register_example, set_rights
from sqlalchemy import Engine


@pytest.fixture
def clip_id(api_engine: Engine) -> int:
    return rendered_clip(api_engine)


def test_queue_needs_source_rights(
    client: TestClient, api_engine: Engine, clip_id: int
) -> None:
    (youtube,) = accounts(api_engine, "youtube")
    post_id = make_draft(client, clip_id, youtube)
    set_rights(api_engine, clip_of(api_engine, clip_id).project_id, None)

    response = client.post(f"/api/posts/{post_id}/queue", json={})

    assert_error(response, 409, "source_rights_missing")
    assert posts.get_post(api_engine, post_id).status == "draft"


def test_queue_needs_a_rendered_clip(client: TestClient, api_engine: Engine) -> None:
    project_id = clip_of(api_engine, rendered_clip(api_engine)).project_id
    unrendered = add_clip(api_engine, project_id, "candidate", 60, "Raw")
    (youtube,) = accounts(api_engine, "youtube")
    post_id = make_draft(client, unrendered, youtube)

    response = client.post(f"/api/posts/{post_id}/queue", json={})

    assert_error(response, 409, "clip_not_rendered")


def test_queue_needs_tiktoks_privacy_choice(
    client: TestClient, api_engine: Engine, clip_id: int
) -> None:
    (tiktok,) = accounts(api_engine, "tiktok")
    post_id = make_draft(client, clip_id, tiktok)

    response = client.post(f"/api/posts/{post_id}/queue", json={})

    assert "privacy" in assert_error(response, 409, "post_not_ready")


def test_queue_needs_the_campaigns_permission(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client)
    project_id = in_campaign(api_engine, campaign["id"])
    set_rights(api_engine, project_id, "permission")
    clip = add_clip(api_engine, project_id, "rendered", 60, "Bit")
    (youtube,) = accounts(api_engine, "youtube")
    post_id = make_draft(client, clip, youtube)

    response = client.post(f"/api/posts/{post_id}/queue", json={})

    assert_error(response, 409, "permission_missing")


def test_queue_refuses_a_past_time(
    client: TestClient, api_engine: Engine, clip_id: int
) -> None:
    (youtube,) = accounts(api_engine, "youtube")
    post_id = make_draft(client, clip_id, youtube)

    response = client.post(
        f"/api/posts/{post_id}/queue", json={"scheduled_at": "2020-01-01T00:00:00Z"}
    )

    assert_error(response, 422, "validation_error")


def test_queue_without_time_publishes_as_soon_as_possible(
    client: TestClient, api_engine: Engine, clip_id: int
) -> None:
    (youtube,) = accounts(api_engine, "youtube")
    post_id = make_draft(client, clip_id, youtube)

    queued = client.post(f"/api/posts/{post_id}/queue", json={"scheduled_at": None})
    again = client.post(f"/api/posts/{post_id}/queue", json={"scheduled_at": LATER})

    assert (queued.json()["status"], queued.json()["scheduled_at"]) == ("queued", None)
    assert_error(again, 409, "invalid_status")


def test_publish_now_uploads_right_away(
    client: TestClient,
    api_engine: Engine,
    clip_id: int,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter,
) -> None:
    register_example(monkeypatch)
    (tiktok,) = accounts(api_engine, "tiktok")
    TokenStore.from_settings().save("ref-tiktok-0", Token(access_token=ACCESS))
    respx_mock.post(VIDEOS_URL).mock(
        return_value=httpx.Response(201, json={"id": "v1", "link": "https://ex/v1"})
    )
    post_id = make_draft(client, clip_id, tiktok, privacy="SELF_ONLY")
    client.post(f"/api/posts/{post_id}/queue", json={"scheduled_at": LATER})

    response = client.post(f"/api/posts/{post_id}/publish")

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["scheduled_at"]) == (
        "queued",
        None,
    )
    post = posts.get_post(api_engine, post_id)
    assert (post.status, post.url, post.attempts) == ("published", "https://ex/v1", 1)


def test_publish_now_needs_the_platforms_developer_app(
    client: TestClient,
    api_engine: Engine,
    clip_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_example(monkeypatch, configured=False)
    (tiktok,) = accounts(api_engine, "tiktok")
    post_id = make_draft(client, clip_id, tiktok, privacy="SELF_ONLY")

    response = client.post(f"/api/posts/{post_id}/publish")

    assert_error(response, 412, "needs_credentials")
    assert posts.get_post(api_engine, post_id).status == "draft"


def test_publish_now_keeps_a_failed_upload_to_retry(
    client: TestClient,
    api_engine: Engine,
    clip_id: int,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter,
) -> None:
    register_example(monkeypatch)
    (tiktok,) = accounts(api_engine, "tiktok")
    TokenStore.from_settings().save("ref-tiktok-0", Token(access_token=ACCESS))
    respx_mock.post(VIDEOS_URL).mock(return_value=httpx.Response(503))
    post_id = make_draft(client, clip_id, tiktok, privacy="SELF_ONLY")

    client.post(f"/api/posts/{post_id}/publish")

    post = posts.get_post(api_engine, post_id)
    assert (post.status, post.attempts) == ("queued", 1)
    assert post.error is not None
