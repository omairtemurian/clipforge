"""Stand-ins for the outside world, in test mode only (the e2e server).

create_test_app mounts this router under /api; a normal server never has
it. Each endpoint does what a platform would do, so the end-to-end tests can
run the app's own code paths without the network:

    POST /testmode/accounts/{platform}          ?name= -> SocialAccount (201)
    POST /testmode/channels/{channel_id}/uploads ?video_id=&title= -> {project_id}
    POST /testmode/posts/{post_id}/publish      -> Post (published)
    GET  /testmode/style-references/{name}.mp4  -> the fixture video

The first is the end of an OAuth sign-in: the account is saved with a
placeholder token in the real token store (test mode's posting worker never
publishes, so the token is never sent). The second is a creator's new
upload seen by Auto Import: the real importer (campaign preset, autopilot
settings, project, its alert) imports it with the fixture video as its
source instead of the YouTube watch page, which test mode cannot download.
The third is the platform taking a queued post: the real publish run (its
checks and status moves) with a publisher that sends nothing and answers a
made-up public link (TEST_POST_URL). The fourth is a video site's direct
file link: a style recipe's reference links point at it, so the real
style fetch (yt-dlp's generic extractor, the limits, the analysis and the
media deletion) downloads the fixture video from this server instead of the
internet.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from sqlalchemy import Engine

from clipforge import posts, social_accounts
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError
from clipforge.auto_import import find_channel
from clipforge.models import Post, SocialAccount, SocialPlatform
from clipforge.oauth import OAuthClient, OAuthSession
from clipforge.oauth_tokens import Token, new_token_ref
from clipforge.publishers.base import (
    AccountProfile,
    Publisher,
    PublishError,
    PublishResult,
    Upload,
)
from clipforge.publishers.publish import publish_post
from clipforge.sources.youtube_feed import FeedEntry
from clipforge.token_store import TokenStore
from clipforge.watch.times import utc_now
from clipforge.watch.youtube_watcher import AutoImporter

FIXTURE_VIDEO = "sample.mp4"
TEST_TOKEN = "test-mode-token"
REFERENCE_NAME = r"^[a-z0-9-]{1,40}$"
TEST_POST_URL = "https://example.com/testmode/{platform}/{post_id}"
TEST_CLIENT = OAuthClient(
    name="Test mode",
    client_id="test-mode",
    client_secret="test-mode",
    authorize_url="https://example.com/testmode/authorize",
    token_url="https://example.com/testmode/token",
    scopes=(),
)

EngineDep = Annotated[Engine, Depends(get_engine)]


@dataclass(frozen=True)
class FixtureUpload(FeedEntry):
    """A feed entry whose project's source is a local fixture video."""

    source: str = ""

    @property
    def url(self) -> str:
        """The fixture video, in place of the watch page."""
        return self.source


class TestModePublisher(Publisher):
    """A platform that takes every upload without a request: the post gets
    the id "test-<post id>" and the link TEST_POST_URL."""

    def __init__(self, platform: SocialPlatform) -> None:
        super().__init__(TEST_CLIENT)
        self.target = platform

    def fetch_account(self, token: Token) -> AccountProfile:
        """Not used: test accounts are saved by connect_test_account."""
        raise PublishError(
            "test-mode accounts are saved directly;"
            " use POST /testmode/accounts/{platform}"
        )

    def upload(self, session: OAuthSession, upload: Upload) -> PublishResult:
        """Answer the post as published, sending nothing."""
        post_id = upload.post.id
        url = TEST_POST_URL.format(platform=self.target, post_id=post_id)
        return PublishResult(external_post_id=f"test-{post_id}", url=url)


def build_router(fixtures_dir: Path) -> APIRouter:
    """Return the test-mode router; uploads use fixtures_dir/sample.mp4."""
    router = APIRouter(prefix="/testmode", include_in_schema=False)

    @router.post("/accounts/{platform}", status_code=201)
    def connect_test_account(
        platform: SocialPlatform, engine: EngineDep, name: str = "Test channel"
    ) -> SocialAccount:
        """Save a connected account called name on platform, as a finished
        sign-in does."""
        token_ref = new_token_ref()
        return social_accounts.save_account(
            engine,
            TokenStore.from_settings(),
            platform,
            AccountProfile(external_id=f"test-{token_ref}", display_name=name),
            Token(access_token=TEST_TOKEN),
            token_ref,
            [],
        )

    @router.post("/channels/{channel_id}/uploads", status_code=201)
    def new_test_upload(
        channel_id: str, video_id: str, title: str, request: Request
    ) -> dict[str, int]:
        """Import a new upload (video_id, title, published now) of the
        watched channel channel_id like Auto Import does; 404 for a channel
        that is not watched, 409 if the video is already known or the
        channel's campaign is closed."""
        importer: AutoImporter = request.app.state.importer
        channel = find_channel(importer.engine, channel_id)
        if channel is None:
            raise ApiError(404, "not_found", f"channel {channel_id} is not watched")
        entry = FixtureUpload(
            video_id=video_id,
            title=title,
            published=utc_now(),
            source=str(fixtures_dir / FIXTURE_VIDEO),
        )
        if not importer._watched(channel):
            raise ApiError(409, "conflict", f"channel {channel_id} is not watched now")
        imported, _ = importer._import_entries(channel, [entry], "push", False)
        if not imported:
            raise ApiError(409, "conflict", f"video {video_id} is already known")
        if importer.on_import is not None:
            importer.on_import()
        return {"project_id": imported[0]}

    @router.post("/posts/{post_id}/publish")
    def publish_test_post(post_id: int, engine: EngineDep) -> Post:
        """Publish the queued post now as its platform would (the real
        publish run and its checks, TestModePublisher as the platform); 404
        for an unknown post, 409 for one that is not queued or may not be
        published."""
        try:
            return publish_post(
                engine,
                post_id,
                TokenStore.from_settings(),
                TestModePublisher,
            )
        except posts.PostNotFound as exc:
            raise ApiError(404, "not_found", str(exc)) from exc
        except posts.IllegalTransition as exc:
            raise ApiError(409, "invalid_status", str(exc)) from exc

    @router.get("/style-references/{name}.mp4")
    def test_style_reference(
        name: Annotated[str, PathParam(pattern=REFERENCE_NAME)],
    ) -> FileResponse:
        """Serve the fixture video as the reference video file name.mp4 (any
        name of lowercase letters, digits and dashes, so a recipe can link
        several references)."""
        return FileResponse(fixtures_dir / FIXTURE_VIDEO, media_type="video/mp4")

    return router
