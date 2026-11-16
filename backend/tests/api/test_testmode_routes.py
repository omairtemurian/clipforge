"""Tests of the test-mode stand-ins (api/testmode_routes.py): a connected
account saved like a finished sign-in, a creator's new upload imported
by the real Auto Import with the fixture video as its source, and a queued
post published by the real publish run without a platform."""

from pathlib import Path
from typing import Any

import pytest
from campaign_api import PERMISSION_URL, add, upload
from clipforge import posts
from clipforge.api.testmode_routes import TEST_TOKEN, build_router
from clipforge.auto_import import channel_videos, find_channel
from clipforge.db import JobRow, ProjectRow
from clipforge.token_store import TokenStore
from fakes import FIXTURES
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from social_fakes import add_account, clip_of, set_rights, write_video
from sqlalchemy import Engine
from sqlmodel import Session, col, select
from youtube_fakes import CHANNEL

UPLOADS = f"/api/testmode/channels/{CHANNEL}/uploads"
NEW_VIDEO = {"video_id": "abcdefghijk", "title": "A new upload"}


@pytest.fixture
def test_client(client: TestClient) -> TestClient:
    """The client of an app with the test-mode router (worker off)."""
    client.app.include_router(  # type: ignore[attr-defined]
        build_router(FIXTURES), prefix="/api"
    )
    return client


def _autopilot_campaign(client: TestClient) -> dict[str, Any]:
    """A campaign watching CHANNEL, with permission evidence and its
    autopilot on (2 clips per source)."""
    campaign = add(
        client,
        source_channel_urls=[f"https://www.youtube.com/channel/{CHANNEL}"],
        permission_source_url=PERMISSION_URL,
        allowed_platforms=["youtube"],
    )
    assert upload(client, campaign["id"]).status_code == 200
    saved = client.put(
        f"/api/campaigns/{campaign['id']}/autopilot",
        json={"enabled": True, "max_clips_per_source": 2},
    )
    assert saved.status_code == 200, saved.text
    return campaign


def test_a_test_account_is_saved_like_a_signed_in_one(
    test_client: TestClient,
) -> None:
    response = test_client.post(
        "/api/testmode/accounts/youtube", params={"name": "Clips channel"}
    )

    assert response.status_code == 201, response.text
    account = response.json()
    assert (account["platform"], account["display_name"], account["is_default"]) == (
        "youtube",
        "Clips channel",
        True,
    )
    assert [a["id"] for a in test_client.get("/api/accounts").json()] == [account["id"]]
    token = TokenStore.from_settings().load(account["token_ref"])
    assert token is not None and token.access_token == TEST_TOKEN


def test_a_new_upload_becomes_an_autopilot_campaign_project(
    test_client: TestClient, api_engine: Engine
) -> None:
    campaign = _autopilot_campaign(test_client)

    response = test_client.post(UPLOADS, params=NEW_VIDEO)

    assert response.status_code == 201, response.text
    project_id = response.json()["project_id"]
    with Session(api_engine) as session:
        project = session.get(ProjectRow, project_id)
        assert project is not None
        job = session.exec(
            select(JobRow).where(col(JobRow.project_id) == project_id)
        ).one()
        assert (project.campaign_id, project.source_rights) == (
            campaign["id"],
            "permission",
        )
        assert project.source_published_at is not None
        assert job.status == "queued"
        assert (project.source_url, project.source_path) == (
            None,
            str(FIXTURES / "sample.mp4"),
        )
        assert project.settings.num_clips == 2
    channel = find_channel(api_engine, CHANNEL)
    assert channel is not None
    videos = channel_videos(api_engine, channel.id)
    assert [(v.video_id, v.project_id) for v in videos] == [("abcdefghijk", project_id)]
    again = test_client.post(UPLOADS, params=NEW_VIDEO)
    assert again.status_code == 409


def test_an_upload_needs_a_watched_channel(test_client: TestClient) -> None:
    unknown = test_client.post(UPLOADS, params=NEW_VIDEO)
    assert unknown.status_code == 404

    campaign = _autopilot_campaign(test_client)
    test_client.patch(f"/api/campaigns/{campaign['id']}", json={"status": "paused"})
    paused = test_client.post(UPLOADS, params=NEW_VIDEO)
    assert paused.status_code == 409


def test_a_normal_server_has_no_test_mode_routes(client: TestClient) -> None:
    response = client.post("/api/testmode/accounts/youtube")
    assert response.status_code in (404, 405)


def _draft_post(engine: Engine) -> int:
    """A draft YouTube post of a rendered clip whose project has rights."""
    project_id = add_project(engine)
    set_rights(engine, project_id, "own")
    clip_id = add_clip(engine, project_id, "rendered", 70)
    output = clip_of(engine, clip_id).output_path
    assert output is not None
    write_video(Path(output))
    account_id = add_account(engine, platform="youtube")
    post = posts.create_post(
        engine, clip_id=clip_id, account_id=account_id, payload={"title": "Bit"}
    )
    return post.id


def test_a_queued_post_is_published_with_a_test_link(
    test_client: TestClient, api_engine: Engine
) -> None:
    post_id = _draft_post(api_engine)
    posts.queue_post(api_engine, post_id, None)

    response = test_client.post(f"/api/testmode/posts/{post_id}/publish")

    assert response.status_code == 200, response.text
    post = response.json()
    assert (
        post["status"],
        post["external_post_id"],
        post["url"],
        post["attempts"],
    ) == (
        "published",
        f"test-{post_id}",
        f"https://example.com/testmode/youtube/{post_id}",
        1,
    )
    assert posts.get_post(api_engine, post_id).status == "published"


def test_only_a_queued_post_is_published(
    test_client: TestClient, api_engine: Engine
) -> None:
    post_id = _draft_post(api_engine)

    draft = test_client.post(f"/api/testmode/posts/{post_id}/publish")
    unknown = test_client.post("/api/testmode/posts/9999/publish")

    assert (draft.status_code, draft.json()["error"]) == (409, "invalid_status")
    assert (unknown.status_code, unknown.json()["error"]) == (404, "not_found")
    assert posts.get_post(api_engine, post_id).status == "draft"


def test_a_style_reference_link_serves_the_fixture_video(
    test_client: TestClient,
) -> None:
    response = test_client.get("/api/testmode/style-references/night-a.mp4")
    ranged = test_client.get(
        "/api/testmode/style-references/night-b.mp4",
        headers={"Range": "bytes=0-99"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.content == (FIXTURES / "sample.mp4").read_bytes()
    assert ranged.status_code == 206
    assert ranged.content == response.content[:100]


def test_a_style_reference_name_is_letters_digits_and_dashes(
    test_client: TestClient,
) -> None:
    response = test_client.get("/api/testmode/style-references/Night_A.mp4")

    assert response.status_code == 422
