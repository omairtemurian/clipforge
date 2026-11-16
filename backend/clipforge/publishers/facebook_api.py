"""Facebook Graph API calls of the Facebook publisher (SPEC-v2 3.10): the
Pages of the signed-in user with their Page access tokens, the requests of
a reel post as a Page, the reel's status, link and collaborator invitations.

Verified 2026-11-01 (docs/decisions.md "TASK-142") on
https://developers.facebook.com/docs/pages-api/getting-started,
https://developers.facebook.com/docs/pages-api/manage-pages and
https://developers.facebook.com/docs/video-api/guides/reels-publishing:
GET /me/accounts (fields id, name, access_token, tasks) lists the Pages the
user manages with a Page access token each (it does not expire when the
user token is long-lived); reels are posted with that Page token, and only
by users who can perform the CREATE_CONTENT task on the Page.
"""

from collections.abc import Callable, Mapping
from typing import Any

import httpx

from clipforge.publishers.base import PublishError
from clipforge.publishers.meta_graph import GRAPH, GraphSession, graph_call

PLATFORM = "Facebook"
PAGES_FIELDS = "id,name,access_token,tasks,picture{url}"
PAGE_SIZE = "100"
MAX_PAGE_REQUESTS = 10
CREATE_TASK = "CREATE_CONTENT"
FACEBOOK_URL = "https://www.facebook.com"


class BearerSession:
    """Sends Graph API requests with one access token (a Page access token,
    or the user token of a fresh sign-in)
    (http makes the HTTP client)."""

    def __init__(self, http: Callable[[], httpx.Client], token: str) -> None:
        self._http = http
        self.token = token

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        **body: Any,
    ) -> httpx.Response:
        """Send a request and return its (read) response."""
        with self._http() as client:
            return client.request(
                method,
                url,
                params=params,
                headers={"Authorization": f"Bearer {self.token}"},
                **body,
            )


def graph(
    session: GraphSession,
    method: str,
    url: str,
    action: str = "post the reel",
    *,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a Graph API request of a reel post and return its answer."""
    return graph_call(session, method, url, action, PLATFORM, params=params, body=body)


def list_pages(session: GraphSession) -> list[dict[str, Any]]:
    """Return the Pages of the session's user (id, name, access_token,
    tasks), following the answer's pages (Graph cursors)."""
    pages: list[dict[str, Any]] = []
    after = ""
    for _ in range(MAX_PAGE_REQUESTS):
        params = {"fields": PAGES_FIELDS, "limit": PAGE_SIZE}
        if after:
            params["after"] = after
        answer = graph(
            session,
            "GET",
            f"{GRAPH}/me/accounts",
            "list your Facebook Pages",
            params=params,
        )
        rows = answer.get("data")
        pages += [
            row
            for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, dict) and row.get("id")
        ]
        paging = answer.get("paging")
        paging = paging if isinstance(paging, dict) else {}
        cursors = paging.get("cursors")
        after = str(cursors.get("after") or "") if isinstance(cursors, dict) else ""
        if not paging.get("next") or not after:
            break
    return pages


def can_create(page: dict[str, Any]) -> bool:
    """Return whether the user may create content on the Page (Facebook's
    CREATE_CONTENT task; a Page answer without tasks is given the benefit
    of the doubt)."""
    tasks = page.get("tasks")
    return not isinstance(tasks, list) or CREATE_TASK in tasks


def reel_status(page: BearerSession, video_id: str) -> dict[str, Any] | None:
    """Return the video's status answer, or None if Facebook does not say
    now (a status that cannot be read never fails the post)."""
    try:
        return graph(
            page,
            "GET",
            f"{GRAPH}/{video_id}",
            "read the reel's status",
            params={"fields": "status"},
        )
    except PublishError:
        return None


def permalink(page: BearerSession, video_id: str) -> str | None:
    """Return the reel's public link, or None if Facebook does not say (the
    reel is published either way)."""
    try:
        answer = graph(
            page,
            "GET",
            f"{GRAPH}/{video_id}",
            "read the reel's link",
            params={"fields": "permalink_url"},
        )
    except PublishError:
        return None
    link = answer.get("permalink_url")
    if not isinstance(link, str) or not link:
        return None
    return f"{FACEBOOK_URL}{link}" if link.startswith("/") else link


def invite_collaborator(page: BearerSession, video_id: str, page_id: str) -> str | None:
    """Invite the Facebook Page page_id to publish the reel too; return why
    it failed (collaborators never fail the post), or None."""
    try:
        answer = graph(
            page,
            "POST",
            f"{GRAPH}/{video_id}/collaborators",
            "invite a collaborator",
            params={"target_id": page_id},
        )
    except PublishError as exc:
        return exc.message
    return None if answer.get("success") is not False else "no reason given"
