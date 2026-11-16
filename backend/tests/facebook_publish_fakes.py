"""Recorded Meta Graph API answers and helpers of the Facebook publisher
tests (tests only).

The JSON files in fixtures/facebook_publish follow the shapes of Meta's
Reels publishing and Pages references (2026-11-01): /me/accounts with each
Page's Page access token and tasks, the reel upload session ({video_id,
upload_url}), the rupload answers, the video status ({status:
{video_status, uploading_phase, processing_phase, publishing_phase}}),
the publish answer ({success}), the permalink and Graph errors. The token
answers, the rupload answers and the generic errors are shared with
fixtures/instagram_publish. The ids and tokens are made up.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import respx
from clipforge import posts
from clipforge.models import Post
from clipforge.oauth_tokens import Token
from clipforge.publishers import facebook
from clipforge.publishers.meta_graph import GRAPH
from clipforge.publishers.publish import publish_post
from clipforge.token_store import TokenStore
from instagram_publish_fakes import (
    ACCESS,
    NOW,
    VIDEO_SIZE,
    lengthen_clip,
    meta_settings,
)
from social_fakes import add_account
from sqlalchemy import Engine
from youtube_publish_fakes import write_sized_video

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PAGE_ID = "104739358734012"
PAGE_TOKEN = "EAAcliplab-page-0012"
VIDEO = "1203457689012345"
PAGES_URL = f"{GRAPH}/me/accounts"
REELS_URL = f"{GRAPH}/{PAGE_ID}/video_reels"
RUPLOAD = f"https://rupload.facebook.com/video-upload/v26.0/{VIDEO}"
VIDEO_URL = f"{GRAPH}/{VIDEO}"
COLLABORATORS_URL = f"{GRAPH}/{VIDEO}/collaborators"


def recorded(name: str) -> dict[str, Any]:
    """Return the recorded JSON fixtures/facebook_publish/<name>.json (or,
    for the shared answers, fixtures/instagram_publish/<name>.json)."""
    path = FIXTURES / "facebook_publish" / f"{name}.json"
    if not path.exists():
        path = FIXTURES / "instagram_publish" / f"{name}.json"
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def answer(status: int, name: str) -> httpx.Response:
    """A recorded answer with the given status."""
    return httpx.Response(status, json=recorded(name))


def make_publisher(sleeps: list[float] | None = None) -> facebook.FacebookPublisher:
    """A publisher whose clock says NOW and whose sleeps are recorded
    instead of waited."""
    client = facebook.facebook_client(meta_settings())
    assert client is not None
    waits = sleeps if sleeps is not None else []
    return facebook.FacebookPublisher(client, clock=NOW.timestamp, sleep=waits.append)


def ready_facebook_post(
    engine: Engine,
    clip_id: int,
    store: TokenStore,
    payload: dict[str, Any] | None = None,
) -> int:
    """Write a 30 s clip's video and queue its post to a connected Facebook
    Page (the user's long-lived token stored); return the post id."""
    lengthen_clip(engine, clip_id)
    write_sized_video(engine, clip_id, VIDEO_SIZE)
    account_id = add_account(engine, PAGE_ID, "facebook")
    store.save(
        f"ref-{PAGE_ID}",
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
        payload=payload if payload is not None else {"description": "A reel"},
    )
    return posts.queue_post(engine, post.id).id


def publish_facebook(
    engine: Engine, post_id: int, store: TokenStore, **kwargs: Any
) -> Post:
    """Publish the post with a test FacebookPublisher."""
    publisher = make_publisher(**kwargs)
    return publish_post(engine, post_id, store, lambda _platform: publisher)


def mock_reel(respx_mock: respx.MockRouter, **answers: Any) -> dict[str, respx.Route]:
    """Mock the Graph calls of a reel post (default: everything works);
    answers replace a route's side effect by its name. "reels" is the list
    of the start and the publish answers."""
    routes = {
        "pages": respx_mock.get(PAGES_URL),
        "reels": respx_mock.post(REELS_URL),
        "rupload": respx_mock.post(RUPLOAD),
        "status": respx_mock.get(VIDEO_URL, params={"fields": "status"}),
        "permalink": respx_mock.get(VIDEO_URL, params={"fields": "permalink_url"}),
        "collaborators": respx_mock.post(COLLABORATORS_URL),
    }
    defaults: dict[str, Any] = {
        "pages": answer(200, "pages"),
        "reels": [answer(200, "reel_start"), answer(200, "publish")],
        "rupload": answer(200, "rupload_ok"),
        "status": [answer(200, "status_processing"), answer(200, "status_published")],
        "permalink": answer(200, "permalink"),
        "collaborators": answer(200, "collaborator"),
    }
    for name, route in routes.items():
        effect = answers.get(name, defaults[name])
        if isinstance(effect, httpx.Response):
            route.mock(return_value=effect)
        else:
            route.mock(side_effect=effect)
    return routes
