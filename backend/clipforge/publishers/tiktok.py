"""The TikTok publisher (SPEC-v2 3.10): the Content Posting API (Direct
Post, FILE_UPLOAD) with the owner's TikTok app (TIKTOK_CLIENT_KEY /
TIKTOK_CLIENT_SECRET).

Verified 2026-11-01 (docs/decisions.md "TASK-140") on
https://developers.tiktok.com/doc/login-kit-desktop,
.../oauth-user-access-token-management, .../tiktok-api-v2-get-user-info,
.../content-posting-api-get-started, .../content-posting-api-reference-*,
.../content-sharing-guidelines and .../tiktok-api-v2-rate-limit:

- Sign-in: Login Kit for Desktop (loopback redirect URI with a port, PKCE
  with the hex SHA-256 challenge), parameters client_key and a
  comma-separated scope; scopes user.info.basic (user/info: open_id,
  display_name) and video.publish (creator_info, video/init, status).
  Access tokens last 24 h, refresh tokens 365 days.
- Post: creator_info/query (latest privacy options, disabled interactions,
  longest video; 20/min per token) -> video/init (6/min per token) ->
  PUT the file to upload_url -> status/fetch (30/min per token) until
  PUBLISH_COMPLETE or FAILED; a public post gets its post id only after
  moderation.
- Unaudited apps: every post is SELF_ONLY, only to private accounts, and
  at most 5 users post through the app per 24 h; the audit lifts it but
  does not accept tools that only post to the owner's own accounts.
  Every app: about 15 posts per creator per 24 h, and the app's daily cap
  of posting creators.
"""

import logging
import mimetypes
import time
from pathlib import Path
from typing import Any

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
from clipforge.publishers.tiktok_api import (
    API,
    CHUNK_BYTES,
    JSON,
    MAX_VIDEO_BYTES,
    SCOPE_MISSING,
    Sleep,
    answer_data,
    chunk_plan,
    post_json,
    send_file,
)
from clipforge.publishers.tiktok_post import (
    CreatorInfo,
    failure,
    options_of,
    post_info,
    result_of,
)

logger = logging.getLogger(__name__)

CLIENT_NAME = "TikTok"
AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = f"{API}/oauth/token/"
USER_INFO_URL = f"{API}/user/info/"
CREATOR_INFO_URL = f"{API}/post/publish/creator_info/query/"
INIT_URL = f"{API}/post/publish/video/init/"
STATUS_URL = f"{API}/post/publish/status/fetch/"
USER_SCOPE = "user.info.basic"
PUBLISH_SCOPE = "video.publish"
SETTINGS_KEYS = ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET")
USER_FIELDS = "open_id,union_id,avatar_url,display_name"
VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}
# Status checks after the upload (STATUS_POLLS x STATUS_WAIT_S s): within
# the 30/min limit; a post still processing then counts as sent.
STATUS_POLLS = 24
STATUS_WAIT_S = 5.0
UNAUDITED = (
    "Unaudited TikTok apps post only as SELF_ONLY (only me), only to private "
    "accounts, and for at most 5 users a day; TikTok's audit lifts this but "
    "does not accept tools that only post to your own accounts."
)
POSTING_CAP = (
    "TikTok allows about 15 posts per account per 24 h through apps, shared "
    "by every app the account uses."
)


def tiktok_client(settings: Settings | None = None) -> OAuthClient | None:
    """Return the TikTok app of the settings, or None when
    TIKTOK_CLIENT_KEY is not set."""
    cfg = settings or config.settings
    client_key = cfg.tiktok_client_key.strip()
    if not client_key:
        return None
    return OAuthClient(
        name=CLIENT_NAME,
        client_id=client_key,
        client_secret=cfg.tiktok_client_secret.strip(),
        authorize_url=AUTHORIZE_URL,
        token_url=TOKEN_URL,
        scopes=(USER_SCOPE, PUBLISH_SCOPE),
        client_id_param="client_key",
        scope_separator=",",
        pkce_hex=True,
    )


def from_settings() -> "TikTokPublisher | None":
    """Return the publisher of the configured TikTok app, or None."""
    client = tiktok_client()
    return TikTokPublisher(client) if client is not None else None


class TikTokPublisher(Publisher):
    """Posts a clip to the connected TikTok account (Direct Post): checks
    the creator's latest info, uploads the file in chunk_bytes chunks and
    follows the post status; sleep waits between tries and checks."""

    platform = "tiktok"

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
        if chunk_bytes <= 0:
            raise ValueError("chunk_bytes must be positive")
        self.sleep = sleep
        self.chunk_bytes = chunk_bytes

    def fetch_account(self, token: Token) -> AccountProfile:
        """Return the account of token (user/info) with TikTok's and the
        account's posting restrictions (creator_info)."""
        auth = {"Authorization": f"Bearer {token.access_token}"}
        restrictions = [UNAUDITED, POSTING_CAP]
        try:
            with self.http() as http:
                user = answer_data(
                    http.get(
                        USER_INFO_URL, params={"fields": USER_FIELDS}, headers=auth
                    ),
                    "name the account",
                ).get("user")
                creator = None
                if PUBLISH_SCOPE in (
                    self.client.granted(token.scope) or [PUBLISH_SCOPE]
                ):
                    creator = self._creator_at_connect(http, auth, restrictions)
                else:
                    restrictions.append(SCOPE_MISSING)
        except httpx.TransportError as exc:
            raise PublishError(f"Cannot reach TikTok: {type(exc).__name__}") from exc
        if not isinstance(user, dict) or not user.get("open_id"):
            raise PublishError("TikTok did not say which account signed in.")
        open_id = str(user["open_id"])
        name = str(user.get("display_name") or "") or open_id
        if creator is not None:
            restrictions.extend(creator.restrictions())
            if creator.username:
                name = f"{creator.nickname or name} (@{creator.username})"
        avatar = user.get("avatar_url")
        return AccountProfile(
            open_id,
            name,
            tuple(restrictions),
            avatar if isinstance(avatar, str) else None,
        )

    def upload(self, session: OAuthSession, upload: Upload) -> PublishResult:
        """Post the clip with its settings and return TikTok's post id and
        link (or the publish_id while TikTok has given no public id)."""
        options = options_of(upload.post.payload)
        mime = _video_type(upload.video)
        size = upload.video.stat().st_size
        if size == 0:
            raise PublishError("The rendered video is empty; render it again.")
        if size > MAX_VIDEO_BYTES:
            raise PublishError("TikTok takes videos of at most 4 GB.")
        if upload.thumbnail is not None:
            logger.info("TikTok takes no cover file; cover_timestamp_ms picks one")
        creator = CreatorInfo.of(
            post_json(session, CREATOR_INFO_URL, None, "check the account")
        )
        info = post_info(options, upload.clip, creator)
        chunk_size, count = chunk_plan(size, self.chunk_bytes)
        started = post_json(
            session,
            INIT_URL,
            {
                "post_info": info,
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": count,
                },
            },
            "start the post",
        )
        publish_id = started.get("publish_id")
        upload_url = started.get("upload_url")
        if not isinstance(publish_id, str) or not isinstance(upload_url, str):
            raise PublishError("TikTok answered the post without an upload link.")
        send_file(
            self.http, upload_url, upload.video, mime, (chunk_size, count), self.sleep
        )
        return result_of(publish_id, self._await(session, publish_id), creator.username)

    def _creator_at_connect(
        self, http: httpx.Client, auth: dict[str, str], restrictions: list[str]
    ) -> CreatorInfo | None:
        """Return the creator's info at sign-in; a refusal (e.g. the daily
        post cap) is noted as a restriction instead of failing the
        connection."""
        try:
            data = answer_data(
                http.post(CREATOR_INFO_URL, headers={**auth, **JSON}),
                "check the account",
            )
        except PublishError as exc:
            restrictions.append(exc.message)
            return None
        return CreatorInfo.of(data)

    def _await(self, session: OAuthSession, publish_id: str) -> dict[str, Any] | None:
        """Follow the post's status until TikTok published it (its status
        data) or failed it (PublishError); None if it is still processing
        after STATUS_POLLS checks or the status cannot be read (the video
        was sent: posting it again would duplicate it)."""
        for _ in range(STATUS_POLLS):
            self.sleep(STATUS_WAIT_S)
            try:
                status = post_json(
                    session, STATUS_URL, {"publish_id": publish_id}, "report the status"
                )
            except PublishError as exc:
                if exc.retryable:
                    continue
                logger.warning("TikTok %s: status unknown: %s", publish_id, exc)
                return None
            if status.get("status") == "PUBLISH_COMPLETE":
                return status
            if status.get("status") == "FAILED":
                raise failure(str(status.get("fail_reason") or ""))
        logger.info("TikTok %s: still processing; counted as sent", publish_id)
        return None


def _video_type(path: Path) -> str:
    """Return the MIME type TikTok takes for the video (MP4, MOV, WebM);
    PublishError (final) for other files."""
    mime = VIDEO_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
    if mime is None or mime not in VIDEO_TYPES.values():
        raise PublishError("TikTok takes MP4, MOV or WebM videos only.")
    return mime
