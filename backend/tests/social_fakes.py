"""A publisher of a made-up platform API and helpers of the publisher
framework tests (tests only). The API (api.example.com) is reached through
respx: nothing leaves the machine."""

from pathlib import Path
from typing import Any

import httpx
import pytest
from clipforge import posts
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import Clip, SocialPlatform
from clipforge.oauth import OAuthClient, OAuthSession
from clipforge.oauth_tokens import Token
from clipforge.publishers import registry
from clipforge.publishers.base import (
    AccountProfile,
    Publisher,
    PublishError,
    PublishResult,
    Upload,
)
from clipforge.social_rows import SocialAccountRow
from sqlalchemy import Engine, update
from sqlmodel import Session, col

API = "https://api.example.com/v1"
ME_URL = f"{API}/me"
VIDEOS_URL = f"{API}/videos"
CLIENT = OAuthClient(
    name="ExampleTube",
    client_id="example-client",
    client_secret="example-secret",
    authorize_url="https://auth.example.com/authorize",
    token_url="https://auth.example.com/token",
    scopes=("video.upload", "user.info"),
)
ACCESS = "example-access-token-1234"
REFRESH = "example-refresh-token-5678"
RESTRICTION = "unaudited app: posts are private"


class ExamplePublisher(Publisher):
    """Posts to ExampleTube: GET /me names the account, POST /videos?title=
    answers the new post {id, link}; 429/5xx answers are retryable."""

    platform = "tiktok"

    def fetch_account(self, token: Token) -> AccountProfile:
        """Ask /me who token belongs to."""
        with self.http() as http:
            response = http.get(
                ME_URL, headers={"Authorization": f"Bearer {token.access_token}"}
            )
        if response.status_code != 200:
            raise PublishError(f"ExampleTube answered {response.status_code}")
        body = response.json()
        restrictions = (RESTRICTION,) if body.get("unaudited") else ()
        return AccountProfile(str(body["id"]), body["name"], restrictions)

    def upload(self, session: OAuthSession, upload: Upload) -> PublishResult:
        """POST the video with its title (the payload's "title")."""
        response = session.request(
            "POST", VIDEOS_URL, params={"title": upload.post.payload.get("title", "")}
        )
        if response.status_code == 429 or response.status_code >= 500:
            raise PublishError("ExampleTube is busy", retryable=True)
        if response.status_code != 201:
            raise PublishError(f"ExampleTube refused: {response.text}")
        body = response.json()
        return PublishResult(body["id"], body["link"])


def register_example(
    monkeypatch: pytest.MonkeyPatch, *, configured: bool = True
) -> None:
    """Make ExamplePublisher the "tiktok" publisher (not configured: its
    factory gives None, as without the OAuth app's settings)."""
    entry = registry.PublisherEntry(
        factory=lambda: ExamplePublisher(CLIENT) if configured else None,
        settings_keys=("EXAMPLE_CLIENT_ID",),
    )
    monkeypatch.setitem(registry.ENTRIES, "tiktok", entry)


def token_answer(**changes: Any) -> httpx.Response:
    """The token endpoint's answer to a code exchange."""
    body = {
        "access_token": ACCESS,
        "refresh_token": REFRESH,
        "expires_in": 3600,
        "scope": "video.upload user.info",
        "token_type": "Bearer",
    }
    return httpx.Response(200, json=body | changes)


def me_answer(
    external_id: str = "acct-1", name: str = "Main channel"
) -> httpx.Response:
    """/me's answer for an account."""
    return httpx.Response(200, json={"id": external_id, "name": name})


def add_account(
    engine: Engine,
    external_id: str = "acct-1",
    platform: SocialPlatform = "tiktok",
    *,
    default: bool = False,
    always_hashtags: list[str] | None = None,
) -> int:
    """Add a connected account row (of platform, its default if default,
    with its always_hashtags) and return its id."""
    with Session(engine) as session:
        row = SocialAccountRow(
            platform=platform,
            external_id=external_id,
            display_name=f"Account {external_id}",
            token_ref=f"ref-{external_id}",
            is_default=default,
            always_hashtags=always_hashtags or [],
        )
        session.add(row)
        session.commit()
        assert row.id is not None
        return row.id


def set_rights(engine: Engine, project_id: int, rights: str | None) -> None:
    """Set the project's source rights (None: unset)."""
    with engine.begin() as conn:
        conn.execute(
            update(ProjectRow)
            .where(col(ProjectRow.id) == project_id)
            .values(source_rights=rights)
        )


def write_video(path: Path) -> Path:
    """Write a stand-in rendered video file at path (its bytes are never
    read: the API is mocked)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    return path


def clip_of(engine: Engine, clip_id: int) -> Clip:
    """Return the stored clip."""
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        return row.to_model()


def add_draft(engine: Engine, clip_id: int, account_id: int | None = None) -> int:
    """Add a draft post of clip_id (to a new account if none is given)."""
    account = account_id or add_account(engine)
    post = posts.create_post(
        engine, clip_id=clip_id, account_id=account, payload={"title": "Bit"}
    )
    return post.id
