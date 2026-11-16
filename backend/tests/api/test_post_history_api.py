"""Tests for the posting history (GET /api/posts/history,
clipforge.post_history): published posts with the links to the live posts,
failed and skipped ones, newest first, filters and paging; and the
post_missed_policy setting of the Settings API."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from clipforge import config, posts
from fastapi.testclient import TestClient
from post_api_fakes import accounts, rendered_clip
from sqlalchemy import Engine

T0 = datetime(2030, 1, 15, 9, 0, tzinfo=UTC)


def add_post(
    engine: Engine, clip_id: int, account_id: int, status: str, hour: int
) -> int:
    """A post of the clip in status, scheduled (and, once tried, started)
    at T0 + hour hours; its id."""
    at = T0 + timedelta(hours=hour)
    post = posts.create_post(
        engine,
        clip_id=clip_id,
        account_id=account_id,
        payload={"title": f"Post {hour}"},
        scheduled_at=at,
    )
    if status == "draft":
        return post.id
    posts.queue_post(engine, post.id, at)
    if status in ("canceled", "skipped"):
        posts.move(engine, post.id, status)  # type: ignore[arg-type]
    elif status != "queued":
        posts.move(engine, post.id, "uploading", attempts=1, attempted_at=at)
        ended: dict[str, Any] = (
            {"url": f"https://ex/{post.id}", "external_post_id": f"x{post.id}"}
            if status == "published"
            else {"error": "Too big"}
        )
        posts.move(engine, post.id, status, **ended)  # type: ignore[arg-type]
    return post.id


@pytest.fixture
def ids(api_engine: Engine) -> dict[str, int]:
    clip_id = rendered_clip(api_engine)
    youtube, tiktok = accounts(api_engine, "youtube", "tiktok")
    return {
        "old_post": add_post(api_engine, clip_id, youtube, "published", 1),
        "failed": add_post(api_engine, clip_id, tiktok, "failed", 2),
        "skipped": add_post(api_engine, clip_id, youtube, "skipped", 3),
        "new_post": add_post(api_engine, clip_id, tiktok, "published", 4),
        "draft": add_post(api_engine, clip_id, tiktok, "draft", 5),
        "queued": add_post(api_engine, clip_id, tiktok, "queued", 6),
        "canceled": add_post(api_engine, clip_id, tiktok, "canceled", 7),
        "youtube": youtube,
    }


def history(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    response = client.get("/api/posts/history", params=params)
    assert response.status_code == 200, response.text
    body: list[dict[str, Any]] = response.json()
    return body


def test_history_lists_what_went_out_newest_first_with_links(
    client: TestClient, ids: dict[str, int]
) -> None:
    listed = history(client)

    assert [post["id"] for post in listed] == [
        ids["new_post"],
        ids["skipped"],
        ids["failed"],
        ids["old_post"],
    ]
    assert listed[0]["url"] == f"https://ex/{ids['new_post']}"
    assert listed[0]["status"] == "published"
    assert listed[2]["error"] == "Too big"


def test_history_filters_and_pages(client: TestClient, ids: dict[str, int]) -> None:
    published = history(client, status="published")
    of_youtube = history(client, account_id=ids["youtube"])
    page = history(client, limit=2, offset=1)

    assert [post["id"] for post in published] == [ids["new_post"], ids["old_post"]]
    assert [post["id"] for post in of_youtube] == [ids["skipped"], ids["old_post"]]
    assert [post["id"] for post in page] == [ids["skipped"], ids["failed"]]
    assert history(client, status="queued") == []
    assert client.get("/api/posts/history", params={"limit": 0}).status_code == 422


def test_the_missed_policy_setting_is_saved_and_read_back(
    client: TestClient, work_in_tmp: Path
) -> None:
    assert client.get("/api/settings").json()["post_missed_policy"] == "post_late"

    response = client.put("/api/settings", json={"post_missed_policy": "skip"})

    assert response.status_code == 200, response.text
    assert response.json()["post_missed_policy"] == "skip"
    assert config.settings.post_missed_policy == "skip"
    fresh = config.Settings(data_dir=config.settings.data_dir)
    assert fresh.post_missed_policy == "skip"
    bad = client.put("/api/settings", json={"post_missed_policy": "later"})
    assert bad.status_code == 422
