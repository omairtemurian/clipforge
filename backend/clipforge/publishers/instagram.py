"""The Instagram publisher (SPEC-v2 3.10): Reels on Instagram professional
accounts (Business or Creator, linked to a Facebook Page) through the
Instagram API with Facebook Login for Business and the owner's Meta app
(META_APP_ID / META_APP_SECRET; meta_graph).

Verified 2026-11-01 (docs/decisions.md "TASK-141") on
https://developers.facebook.com/docs/instagram-platform/content-publishing,
.../instagram-platform/instagram-api-with-facebook-login/get-started,
.../instagram-graph-api/reference/ig-user/media,
.../instagram-graph-api/reference/ig-container and
.../instagram-graph-api/reference/error-codes:

- Sign-in: permissions instagram_basic, instagram_content_publish,
  pages_show_list and pages_read_engagement; the Instagram account is the
  instagram_business_account of a Page the user manages (/me/accounts).
- Post: POST /{ig-user}/media (media_type REELS, upload_type resumable)
  -> POST the file to the container's rupload.facebook.com uri ->
  GET /{container}?fields=status_code until FINISHED (once a minute, at
  most 5 minutes) -> POST /{ig-user}/media_publish (creation_id).
  Uploading from this machine needs Facebook Login for Business (the
  Instagram Login API takes public video_url links only).
- Limits: 100 API posts per account per moving 24 h
  (content_publishing_limit); containers expire after 24 h. Standard
  Access serves only people with a role on the Meta app; other accounts
  need Advanced Access (App Review and Business Verification).
"""

import logging

import httpx

from clipforge.config import Settings
from clipforge.oauth import OAuthClient, OAuthSession
from clipforge.oauth_tokens import Token
from clipforge.publishers.base import (
    AccountProfile,
    PublishError,
    PublishResult,
    Upload,
)
from clipforge.publishers.instagram_api import (
    PLATFORM,
    check_limit,
    graph,
    instagram_accounts,
    limit_note,
)
from clipforge.publishers.instagram_post import (
    check_video,
    container_body,
    options_of,
    status_failure,
)
from clipforge.publishers.meta_graph import (
    GRAPH,
    MetaPublisher,
    answer_json,
    meta_client,
)
from clipforge.publishers.meta_graph import SETTINGS_KEYS as META_SETTINGS_KEYS
from clipforge.publishers.meta_upload import MAX_UPLOAD_TRIES, send_video

logger = logging.getLogger(__name__)

SETTINGS_KEYS = META_SETTINGS_KEYS
PUBLISH_SCOPE = "instagram_content_publish"
SCOPES = ("instagram_basic", PUBLISH_SCOPE, "pages_show_list", "pages_read_engagement")
PAGES_FIELDS = (
    "id,name,instagram_business_account{id,username,name,profile_picture_url}"
)
# Container status checks (Meta: once a minute for at most 5 minutes).
STATUS_POLLS = 5
STATUS_WAIT_S = 60.0
UNAUDITED = (
    "Without Meta's App Review (Advanced Access) the Meta app posts only for "
    "people with a role on the app; posting for other accounts needs App "
    "Review and Business Verification."
)
POSTING_CAP = "Instagram allows 100 API posts per account per 24 h."
REEL_RULES = (
    "Reels only (MP4/MOV, 3 s to 15 min, at most 300 MB); Instagram takes no "
    "cover file from this machine: thumb_offset_ms picks the cover frame."
)
SCOPE_MISSING = (
    "The instagram_content_publish permission was not granted; connect the "
    "account again and allow it, or posting will fail."
)


def instagram_client(settings: Settings | None = None) -> OAuthClient | None:
    """Return the Meta app of the settings signing in for Instagram, or
    None while META_APP_ID or META_APP_SECRET is not set."""
    return meta_client(PLATFORM, SCOPES, settings)


def from_settings() -> "InstagramPublisher | None":
    """Return the publisher of the configured Meta app, or None."""
    client = instagram_client()
    return InstagramPublisher(client) if client is not None else None


class InstagramPublisher(MetaPublisher):
    """Posts a clip as a reel to the connected Instagram professional
    account."""

    platform = "instagram"

    def fetch_account(self, token: Token) -> AccountProfile:
        """Return the Instagram professional account of the user's Pages
        (the first by username if there are several) with Instagram's
        restrictions and the account's publishing limit."""
        auth = {"Authorization": f"Bearer {token.access_token}"}
        restrictions = [UNAUDITED, POSTING_CAP, REEL_RULES]
        if PUBLISH_SCOPE not in (self.client.granted(token.scope) or [PUBLISH_SCOPE]):
            restrictions.append(SCOPE_MISSING)
        try:
            with self.http() as http:
                pages = answer_json(
                    http.get(
                        f"{GRAPH}/me/accounts",
                        params={"fields": PAGES_FIELDS},
                        headers=auth,
                    ),
                    "list your Facebook Pages",
                    PLATFORM,
                )
                accounts = instagram_accounts(pages)
                if not accounts:
                    raise PublishError(
                        "None of your Facebook Pages has an Instagram professional "
                        "account; switch the Instagram account to Business or "
                        "Creator and link it to a Page."
                    )
                chosen = accounts[0]
                if len(accounts) > 1:
                    others = ", ".join(f"@{a['username']}" for a in accounts[1:])
                    restrictions.append(
                        f"Connected @{chosen['username']}; your Pages also link "
                        f"{others} (one account per connection)."
                    )
                restrictions.append(limit_note(http, auth, chosen["id"]))
        except httpx.TransportError as exc:
            raise PublishError(f"Cannot reach Instagram: {type(exc).__name__}") from exc
        name = chosen["name"] or chosen["username"]
        return AccountProfile(
            chosen["id"],
            f"{name} (@{chosen['username']})",
            tuple(restrictions),
            chosen.get("avatar") or None,
        )

    def upload(self, session: OAuthSession, upload: Upload) -> PublishResult:
        """Post the clip as a reel and return its media id and link."""
        ig_user = upload.account_external_id
        if not ig_user:
            raise PublishError("The Instagram account id is unknown; connect again.")
        options = options_of(upload.post.payload)
        size = check_video(upload.video, upload.clip)
        body = container_body(options, upload.clip)
        if upload.thumbnail is not None:
            logger.info("Instagram takes no cover file; thumb_offset_ms picks one")
        check_limit(session, ig_user)
        container = graph(session, "POST", f"{GRAPH}/{ig_user}/media", body=body)
        container_id = container.get("id")
        upload_uri = container.get("uri")
        if not isinstance(container_id, str) or not container_id:
            raise PublishError("Instagram did not create the reel.", retryable=True)
        if not isinstance(upload_uri, str) or not upload_uri:
            upload_uri = f"https://rupload.facebook.com/ig-api-upload/{container_id}"
        send_video(
            PLATFORM,
            self.http,
            upload_uri,
            session.access_token,
            (upload.video, size),
            self.sleep,
            MAX_UPLOAD_TRIES,
        )
        self._await(session, container_id)
        try:
            published = graph(
                session,
                "POST",
                f"{GRAPH}/{ig_user}/media_publish",
                body={"creation_id": container_id},
            )
        except PublishError as exc:
            if exc.retryable and self._status(session, container_id)[0] == "PUBLISHED":
                return PublishResult(container_id, None)
            raise
        media_id = str(published.get("id") or container_id)
        return PublishResult(media_id, self._permalink(session, media_id))

    def _status(self, session: OAuthSession, container_id: str) -> tuple[str, str]:
        """Return the container's status_code and status ("" if unknown)."""
        try:
            answer = graph(
                session,
                "GET",
                f"{GRAPH}/{container_id}",
                params={"fields": "status_code,status"},
            )
        except PublishError as exc:
            logger.info("Instagram %s: status unknown: %s", container_id, exc)
            return "", ""
        return str(answer.get("status_code") or ""), str(answer.get("status") or "")

    def _await(self, session: OAuthSession, container_id: str) -> None:
        """Wait until Instagram processed the video (FINISHED); PublishError
        if it failed or is still processing after STATUS_POLLS checks."""
        for _ in range(STATUS_POLLS):
            self.sleep(STATUS_WAIT_S)
            status_code, status = self._status(session, container_id)
            if status_code in ("FINISHED", "PUBLISHED"):
                return
            if status_code in ("ERROR", "EXPIRED"):
                raise status_failure(status_code, status)
        raise PublishError(
            "Instagram is still processing the reel; the post is tried again later.",
            retryable=True,
        )

    def _permalink(self, session: OAuthSession, media_id: str) -> str | None:
        """Return the reel's public link, or None if Instagram does not say
        (the reel is published either way)."""
        try:
            answer = graph(
                session, "GET", f"{GRAPH}/{media_id}", params={"fields": "permalink"}
            )
        except PublishError as exc:
            logger.info("Instagram %s: no permalink: %s", media_id, exc)
            return None
        link = answer.get("permalink")
        return link if isinstance(link, str) and link else None
