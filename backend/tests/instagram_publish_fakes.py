"""Recorded Meta Graph API answers and helpers of the Instagram publisher
tests (tests only).

The JSON files in fixtures/instagram_publish follow the shapes of Meta's
references (2026-11-01): the oauth/access_token answers (short- and
long-lived user tokens), /me/permissions, /me/accounts with each Page's
instagram_business_account, content_publishing_limit, the media container
({id, uri}), the rupload answers ({success} or {debug_info}), the
container status codes (IN_PROGRESS, FINISHED, PUBLISHED, EXPIRED, ERROR
with its error subcode), media_publish, the permalink and Graph errors
({"error": {message, type, code, error_subcode, is_transient, ...}}). The
ids and tokens are made up.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from clipforge import config, posts
from clipforge.db import ClipRow
from clipforge.models import Post
from clipforge.oauth_tokens import Token
from clipforge.publishers import instagram
from clipforge.publishers.meta_graph import GRAPH
from clipforge.publishers.publish import publish_post
from clipforge.token_store import TokenStore
from social_fakes import add_account
from sqlalchemy import Engine
from sqlmodel import Session
from youtube_publish_fakes import write_sized_video

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "instagram_publish"
APP_ID = "1234567890123456"
APP_SECRET = "meta-cliplab-secret"
CONFIG_ID = "987654321098765"
IG_USER = "17841400008460056"
CONTAINER = "17889455560051444"
MEDIA = "18027939643180851"
ACCESS = "EAAcliplab-long-0001"
RUPLOAD = f"https://rupload.facebook.com/ig-api-upload/v26.0/{CONTAINER}"
MEDIA_URL = f"{GRAPH}/{IG_USER}/media"
PUBLISH_URL = f"{GRAPH}/{IG_USER}/media_publish"
LIMIT_URL = f"{GRAPH}/{IG_USER}/content_publishing_limit"
CONTAINER_URL = f"{GRAPH}/{CONTAINER}"
MEDIA_ITEM_URL = f"{GRAPH}/{MEDIA}"
NOW = datetime(2026, 11, 1, 7, 30, tzinfo=UTC)
VIDEO_SIZE = 2600


def recorded(name: str) -> dict[str, Any]:
    """Return the recorded JSON fixtures/instagram_publish/<name>.json."""
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text())
    return data


def answer(status: int, name: str) -> httpx.Response:
    """A recorded answer with the given status."""
    return httpx.Response(status, json=recorded(name))


def meta_settings(app_id: str = APP_ID, config_id: str = "") -> config.Settings:
    """The app settings with a Meta app (keeps the data_dir)."""
    return config.settings.model_copy(
        update={
            "meta_app_id": app_id,
            "meta_app_secret": APP_SECRET if app_id else "",
            "meta_login_config_id": config_id,
        }
    )


def configure_meta(
    monkeypatch: pytest.MonkeyPatch, app_id: str = APP_ID, config_id: str = ""
) -> None:
    """Set the Meta app in config.settings ("" : not configured)."""
    monkeypatch.setattr(config, "settings", meta_settings(app_id, config_id))


def make_publisher(sleeps: list[float] | None = None) -> instagram.InstagramPublisher:
    """A publisher whose clock says NOW and whose sleeps are recorded
    instead of waited."""
    client = instagram.instagram_client(meta_settings())
    assert client is not None
    waits = sleeps if sleeps is not None else []
    return instagram.InstagramPublisher(client, clock=NOW.timestamp, sleep=waits.append)


def lengthen_clip(engine: Engine, clip_id: int, seconds: float = 30.0) -> None:
    """Make the clip play for seconds (the seeded clip lasts 2.5 s, under
    Instagram's 3 s minimum)."""
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        row.segments = [(10.0, 10.0 + seconds)]
        row.cut_ranges = []
        session.add(row)
        session.commit()


def ready_instagram_post(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    payload: dict[str, Any] | None = None,
) -> int:
    """Write a 30 s clip's video and queue its post to a connected
    Instagram account (its long-lived token stored); return the post id."""
    lengthen_clip(engine, clip_id)
    write_sized_video(engine, clip_id, VIDEO_SIZE)
    account_id = add_account(engine, IG_USER, "instagram")
    store.save(
        f"ref-{IG_USER}",
        Token(
            access_token=ACCESS,
            refresh_token=None,
            expires_at=NOW.timestamp() + 5_000_000,
        ),
    )
    post = posts.create_post(
        engine,
        clip_id=clip_id,
        account_id=account_id,
        payload=payload if payload is not None else {"caption": "A reel"},
    )
    return posts.queue_post(engine, post.id).id


def publish_instagram(
    engine: Engine, post_id: int, store: TokenStore, **kwargs: Any
) -> Post:
    """Publish the post with a test InstagramPublisher."""
    publisher = make_publisher(**kwargs)
    return publish_post(engine, post_id, store, lambda _platform: publisher)


def mock_reel(respx_mock: respx.MockRouter, **answers: Any) -> dict[str, respx.Route]:
    """Mock the Graph calls of a reel post (default: everything works);
    answers replace a route's side effect by its name."""
    routes = {
        "limit": respx_mock.get(LIMIT_URL),
        "media": respx_mock.post(MEDIA_URL),
        "rupload": respx_mock.post(RUPLOAD),
        "status": respx_mock.get(CONTAINER_URL),
        "publish": respx_mock.post(PUBLISH_URL),
        "permalink": respx_mock.get(MEDIA_ITEM_URL),
    }
    defaults: dict[str, Any] = {
        "limit": answer(200, "publishing_limit"),
        "media": answer(200, "container"),
        "rupload": answer(200, "rupload_ok"),
        "status": [answer(200, "status_in_progress"), answer(200, "status_finished")],
        "publish": answer(200, "publish"),
        "permalink": answer(200, "permalink"),
    }
    for name, route in routes.items():
        effect = answers.get(name, defaults[name])
        if isinstance(effect, httpx.Response):
            route.mock(return_value=effect)
        else:
            route.mock(side_effect=effect)
    return routes
