"""The YouTube publisher (SPEC-v2 3.10): YouTube Data API v3 with the
owner's Google OAuth app (the one of the Drive import, GOOGLE_OAUTH_*).

Verified 2026-11-01 (docs/decisions.md "TASK-139") on
https://developers.google.com/youtube/data/reference/rest/v3 (videos.insert,
thumbnails.set, channels.list), .../getting-started#quota,
.../determine_quota_cost and .../revision_history:

- Scopes: youtube.upload (videos.insert, thumbnails.set) and
  youtube.readonly (channels.list mine=true: who connected).
- Quotas per Google Cloud project, reset at midnight Pacific Time:
  videos.insert has its own bucket (100 calls a day, 1 unit each, since
  June 2026); every other method shares 10,000 units a day (channels.list
  1, thumbnails.set 50). Any request, even a failed one, is charged.
- Review: more quota needs YouTube's quota extension form and an API
  compliance audit; uploads from unaudited projects (created after
  2020-07-28) were locked private by the 2020 rule, which the current
  videos reference no longer states, so the account shows it as a may.
- The upload is resumable (youtube_upload); a custom thumbnail goes up
  with thumbnails.set (JPEG/PNG, at most 50 MB) after the video.
"""

import logging
import mimetypes
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from clipforge import config
from clipforge.config import Settings
from clipforge.oauth import Clock, OAuthClient, OAuthSession
from clipforge.oauth_tokens import Token
from clipforge.publishers.base import (
    AccountProfile,
    Publisher,
    PublishError,
    PublishResult,
    Upload,
)
from clipforge.publishers.quota import DailyQuota
from clipforge.publishers.youtube_metadata import options_of, video_resource
from clipforge.publishers.youtube_upload import (
    CHUNK_BYTES,
    CHUNK_UNIT,
    Sleep,
    api_error,
    send_file,
    start_session,
)
from clipforge.sources.gdrive import AUTHORIZE_URL, TOKEN_URL

logger = logging.getLogger(__name__)

CLIENT_NAME = "YouTube"
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
WATCH_URL = "https://www.youtube.com/watch?v="
SETTINGS_KEYS = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET")
THUMBNAIL_MAX_BYTES = 50 * 1024 * 1024
CHANNELS_LIST_UNITS = 1
THUMBNAILS_SET_UNITS = 50
PACIFIC = ZoneInfo("America/Los_Angeles")
UPLOADS = DailyQuota(
    "youtube_uploads",
    lambda: config.settings.youtube_daily_uploads,
    PACIFIC,
    "YouTube upload (videos.insert)",
)
UNITS = DailyQuota(
    "youtube_quota_units",
    lambda: config.settings.youtube_daily_quota_units,
    PACIFIC,
    "YouTube Data API",
)
# What one upload spends (posting worker quota guard): one videos.insert.
UPLOAD_QUOTAS = ((UPLOADS, 1.0),)
UNAUDITED = (
    "Unaudited Google Cloud projects: YouTube may keep uploads private until "
    "the project passes the YouTube API Services compliance audit."
)


def youtube_client(settings: Settings | None = None) -> OAuthClient | None:
    """Return the YouTube OAuth app (the Google OAuth app of the settings),
    or None when GOOGLE_OAUTH_CLIENT_ID is not set. Google shows its account
    chooser each time, so several channels can be connected."""
    cfg = settings or config.settings
    client_id = cfg.google_oauth_client_id.strip()
    if not client_id:
        return None
    return OAuthClient(
        name=CLIENT_NAME,
        client_id=client_id,
        client_secret=cfg.google_oauth_client_secret.strip(),
        authorize_url=AUTHORIZE_URL,
        token_url=TOKEN_URL,
        scopes=(UPLOAD_SCOPE, READONLY_SCOPE),
        authorize_params={"prompt": "select_account"},
    )


def from_settings() -> "YouTubePublisher | None":
    """Return the publisher of the configured Google OAuth app, or None."""
    client = youtube_client()
    return YouTubePublisher(client) if client is not None else None


class YouTubePublisher(Publisher):
    """Uploads a post's clip to the connected channel (resumable, in
    chunk_bytes chunks; sleep waits between resumes) and sets its
    thumbnail; every call's quota units are guarded and metered."""

    platform = "youtube"

    def __init__(
        self,
        client: OAuthClient,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Clock = time.time,
        sleep: Sleep = time.sleep,
        chunk_bytes: int = CHUNK_BYTES,
    ) -> None:
        super().__init__(client, transport=transport, clock=clock)
        if chunk_bytes <= 0 or chunk_bytes % CHUNK_UNIT:
            raise ValueError("chunk_bytes must be a multiple of 256 KiB")
        self.sleep = sleep
        self.chunk_bytes = chunk_bytes

    def fetch_account(self, token: Token) -> AccountProfile:
        """Return the channel of token (channels.list mine=true) with the
        app's and the channel's upload restrictions."""
        UNITS.spend(CHANNELS_LIST_UNITS, self._now())
        try:
            with self.http() as http:
                response = http.get(
                    CHANNELS_URL,
                    params={"part": "snippet,status", "mine": "true"},
                    headers={"Authorization": f"Bearer {token.access_token}"},
                )
        except httpx.TransportError as exc:
            raise PublishError(f"Cannot reach YouTube: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise api_error(response, "name the channel")
        items = response.json().get("items") or []
        if not items:
            raise PublishError(
                "This Google account has no YouTube channel; create one first."
            )
        channel: dict[str, Any] = items[0]
        title = str(channel.get("snippet", {}).get("title") or channel["id"])
        thumbnails = channel.get("snippet", {}).get("thumbnails") or {}
        avatar = (thumbnails.get("default") or {}).get("url")
        return AccountProfile(
            str(channel["id"]), title, self._restrictions(channel), avatar
        )

    def upload(self, session: OAuthSession, upload: Upload) -> PublishResult:
        """Upload the clip with its metadata, then its thumbnail (if any);
        return the video id and watch link."""
        options = options_of(upload.post.payload)
        video = video_resource(
            options, upload.clip, upload.post.scheduled_at, self._now()
        )
        size = upload.video.stat().st_size
        if size == 0:
            raise PublishError("The rendered video is empty; render it again.")
        mime = _media_type(upload.video, "video/")
        UPLOADS.spend(1, self._now())
        params = {
            "part": "snippet,status",
            "notifySubscribers": "true" if options.notify_subscribers else "false",
        }
        session_url = start_session(session, video, params, size, mime)
        created = send_file(
            session,
            session_url,
            upload.video,
            mime,
            chunk_bytes=self.chunk_bytes,
            sleep=self.sleep,
        )
        _check_upload_status(created)
        video_id = str(created["id"])
        if upload.thumbnail is not None:
            self._set_thumbnail(session, video_id, upload.thumbnail)
        return PublishResult(video_id, WATCH_URL + video_id)

    def _set_thumbnail(self, session: OAuthSession, video_id: str, path: Path) -> None:
        """Set the video's custom thumbnail. The video is already up, so a
        failure is logged and the post stays published."""
        if not path.is_file() or path.stat().st_size > THUMBNAIL_MAX_BYTES:
            logger.warning("YouTube %s: thumbnail missing or over 50 MB", video_id)
            return
        try:
            UNITS.spend(THUMBNAILS_SET_UNITS, self._now())
            response = session.request(
                "POST",
                THUMBNAIL_URL,
                params={"videoId": video_id, "uploadType": "media"},
                content=path.read_bytes(),
                headers={"Content-Type": _media_type(path, "image/")},
            )
        except (PublishError, httpx.TransportError) as exc:
            logger.warning("YouTube %s: thumbnail not set: %s", video_id, exc)
            return
        if response.status_code != 200:
            error = api_error(response, "set the thumbnail")
            logger.warning("YouTube %s: %s", video_id, error.message)

    def _restrictions(self, channel: dict[str, Any]) -> tuple[str, ...]:
        """Return what limits uploads of this app and channel."""
        cfg = config.settings
        found = [
            f"Daily limits of your Google Cloud project: "
            f"{cfg.youtube_daily_uploads} uploads and "
            f"{cfg.youtube_daily_quota_units} other API units (reset at midnight "
            "Pacific Time); more needs YouTube's quota extension and audit.",
            UNAUDITED,
        ]
        status = channel.get("status") or {}
        if status.get("isLinked") is False:
            found.append(
                "The channel has no public YouTube identity yet; uploads need one."
            )
        long_uploads = status.get("longUploadsStatus")
        if long_uploads is not None and long_uploads != "allowed":
            found.append(
                "Videos longer than 15 minutes need a verified channel "
                f"(long uploads: {long_uploads})."
            )
        return tuple(found)

    def _now(self) -> datetime:
        """Return the clock's time as an aware datetime."""
        return datetime.fromtimestamp(self.clock(), UTC)


def _check_upload_status(video: dict[str, Any]) -> None:
    """Raise PublishError (final) if YouTube rejected or failed the upload
    it answered (status.uploadStatus rejected/failed)."""
    status = video.get("status") or {}
    upload_status = status.get("uploadStatus")
    if upload_status == "rejected":
        reason = status.get("rejectionReason", "no reason given")
        raise PublishError(f"YouTube rejected the video ({reason}).")
    if upload_status == "failed":
        reason = status.get("failureReason", "no reason given")
        raise PublishError(f"YouTube could not process the video ({reason}).")


def _media_type(path: Path, family: str) -> str:
    """Return path's MIME type if it is in family ("video/", "image/"),
    else application/octet-stream (both accepted by YouTube)."""
    guessed = mimetypes.guess_type(path.name)[0]
    return (
        guessed
        if guessed and guessed.startswith(family)
        else ("application/octet-stream")
    )
