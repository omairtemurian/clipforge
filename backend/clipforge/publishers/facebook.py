"""The Facebook publisher (SPEC-v2 3.10): reels on Facebook Pages through
Facebook Login for Business and the owner's Meta app (META_APP_ID /
META_APP_SECRET; meta_graph), the same app as the Instagram publisher.

Verified 2026-11-01 (docs/decisions.md "TASK-142") on
https://developers.facebook.com/docs/video-api/guides/reels-publishing,
https://developers.facebook.com/docs/pages-api/getting-started,
https://developers.facebook.com/docs/graph-api/reference/page/video_reels
and https://developers.facebook.com/docs/permissions:

- Sign-in: permissions pages_show_list, pages_read_engagement and
  pages_manage_posts; the account is a Page the user can create content on
  (/me/accounts), posted to with that Page's access token.
- Post: POST /{page}/video_reels (upload_phase start) -> POST the file to
  the returned rupload.facebook.com upload_url -> POST /{page}/video_reels
  (upload_phase finish, video_state PUBLISHED, description, title) ->
  GET /{video}?fields=status until published.
- Limits: 30 API-published reels per Page per moving 24 h (Meta reports no
  use of it: it is enforced when the reel is published). Standard Access
  serves only people with a role on the Meta app; other people's Pages
  need Advanced Access (App Review and Business Verification).
"""

import logging

from clipforge.config import Settings
from clipforge.oauth import OAuthClient, OAuthSession
from clipforge.oauth_tokens import Token
from clipforge.publishers.base import (
    AccountProfile,
    PublishError,
    PublishResult,
    Upload,
)
from clipforge.publishers.facebook_api import (
    PLATFORM,
    BearerSession,
    can_create,
    graph,
    invite_collaborator,
    list_pages,
    permalink,
    reel_status,
)
from clipforge.publishers.facebook_post import (
    check_video,
    options_of,
    publish_body,
    reel_state,
)
from clipforge.publishers.meta_graph import GRAPH, MetaPublisher, meta_client
from clipforge.publishers.meta_graph import SETTINGS_KEYS as META_SETTINGS_KEYS
from clipforge.publishers.meta_upload import MAX_UPLOAD_TRIES, send_video

logger = logging.getLogger(__name__)

SETTINGS_KEYS = META_SETTINGS_KEYS
PUBLISH_SCOPE = "pages_manage_posts"
SCOPES = ("pages_show_list", "pages_read_engagement", PUBLISH_SCOPE)
# Status checks after the reel was sent for publishing.
STATUS_POLLS = 12
STATUS_WAIT_S = 10.0
UNAUDITED = (
    "Without Meta's App Review (Advanced Access) the Meta app posts only to "
    "Pages managed by people with a role on the app; posting to other "
    "people's Pages needs App Review and Business Verification."
)
POSTING_CAP = (
    "Facebook allows 30 API-published reels per Page per 24 h; it reports no "
    "use of this limit, so ClipForge cannot check it before posting."
)
REEL_RULES = (
    "Reels only (MP4, 3 to 90 s, 9:16, at least 540x960, 24 to 60 fps); "
    "reels are public and go live at once (ClipForge's scheduler decides "
    "when); ClipForge sends no cover image."
)
SCOPE_MISSING = (
    "The pages_manage_posts permission was not granted; connect the Page "
    "again and allow it, or posting will fail."
)
NO_PAGE = (
    "You cannot post as this Facebook Page (any more); connect it again as "
    "a person who can create content on it."
)


def facebook_client(settings: Settings | None = None) -> OAuthClient | None:
    """Return the Meta app of the settings signing in for Facebook, or None
    while META_APP_ID or META_APP_SECRET is not set."""
    return meta_client(PLATFORM, SCOPES, settings)


def from_settings() -> "FacebookPublisher | None":
    """Return the publisher of the configured Meta app, or None."""
    client = facebook_client()
    return FacebookPublisher(client) if client is not None else None


class FacebookPublisher(MetaPublisher):
    """Posts a clip as a reel to the connected Facebook Page."""

    platform = "facebook"

    def fetch_account(self, token: Token) -> AccountProfile:
        """Return the first (by name) of the user's Pages that they can
        create content on, with Facebook's restrictions."""
        restrictions = [UNAUDITED, POSTING_CAP, REEL_RULES]
        if PUBLISH_SCOPE not in (self.client.granted(token.scope) or [PUBLISH_SCOPE]):
            restrictions.append(SCOPE_MISSING)
        pages = list_pages(BearerSession(self.http, token.access_token))
        postable = sorted(
            (p for p in pages if can_create(p)),
            key=lambda p: str(p.get("name")).lower(),
        )
        if not postable:
            raise PublishError(
                "None of your Facebook Pages lets you create content; ask a Page "
                "admin for full or content access, and allow the Page in "
                "Facebook's permission dialog."
            )
        chosen = postable[0]
        if len(postable) > 1:
            others = ", ".join(str(p.get("name")) for p in postable[1:])
            restrictions.append(
                f"Connected {chosen.get('name')}; you also manage {others} "
                "(one Page per connection: choose a single Page in Facebook's "
                "permission dialog)."
            )
        name = str(chosen.get("name") or chosen["id"])
        picture = chosen.get("picture")
        data = picture.get("data") if isinstance(picture, dict) else None
        avatar = data.get("url") if isinstance(data, dict) else None
        return AccountProfile(
            str(chosen["id"]),
            name,
            tuple(restrictions),
            avatar if isinstance(avatar, str) else None,
        )

    def upload(self, session: OAuthSession, upload: Upload) -> PublishResult:
        """Post the clip as a reel and return its video id and link."""
        page_id = upload.account_external_id
        if not page_id:
            raise PublishError("The Facebook Page id is unknown; connect again.")
        options = options_of(upload.post.payload)
        size = check_video(upload.video, upload.clip)
        if upload.thumbnail is not None:
            logger.info("Facebook reels take no cover file from ClipForge")
        page = self._page_session(session, page_id)
        started = graph(
            page,
            "POST",
            f"{GRAPH}/{page_id}/video_reels",
            body={"upload_phase": "start"},
        )
        video_id = started.get("video_id")
        upload_url = started.get("upload_url")
        if not isinstance(video_id, str) or not isinstance(upload_url, str):
            raise PublishError(
                "Facebook did not start the reel upload.", retryable=True
            )
        send_video(
            PLATFORM,
            self.http,
            upload_url,
            lambda: page.token,
            (upload.video, size),
            self.sleep,
            MAX_UPLOAD_TRIES,
        )
        body = publish_body(options, upload.clip, video_id)
        self._publish(page, page_id, video_id, body)
        self._await(page, video_id)
        for collaborator in options.collaborator_page_ids:
            problem = invite_collaborator(page, video_id, collaborator)
            if problem:
                logger.info("Facebook %s: no invitation: %s", collaborator, problem)
        return PublishResult(video_id, permalink(page, video_id))

    def _page_session(self, session: OAuthSession, page_id: str) -> BearerSession:
        """Return a session that sends requests as the Page page_id; the
        user's token (refreshed if needed) finds its Page access token."""
        pages = list_pages(session)
        page = next((p for p in pages if str(p["id"]) == page_id), None)
        token = page.get("access_token") if page is not None else None
        if (
            page is None
            or not can_create(page)
            or not isinstance(token, str)
            or not token
        ):
            raise PublishError(NO_PAGE)
        return BearerSession(self.http, token)

    def _publish(
        self, page: BearerSession, page_id: str, video_id: str, body: dict[str, object]
    ) -> None:
        """End the upload session and publish; a publish call without
        answer that went through is not repeated."""
        try:
            graph(page, "POST", f"{GRAPH}/{page_id}/video_reels", body=body)
        except PublishError as exc:
            if not exc.retryable:
                raise
            status = reel_status(page, video_id)
            if status is None or reel_state(status)[0] != "published":
                raise

    def _await(self, page: BearerSession, video_id: str) -> None:
        """Wait until Facebook says the reel is published; PublishError if
        it failed. A reel still processing after STATUS_POLLS checks was
        accepted and goes live by itself (it is not sent again)."""
        for attempt in range(STATUS_POLLS):
            if attempt:
                self.sleep(STATUS_WAIT_S)
            status = reel_status(page, video_id)
            state, error = (
                reel_state(status) if status is not None else ("pending", None)
            )
            if state == "published":
                return
            if error is not None:
                raise error
        logger.info("Facebook %s: still processing; it goes live by itself", video_id)
