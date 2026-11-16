"""Instagram Graph API calls of the Instagram publisher (SPEC-v2 3.10):
the Graph requests of a reel post, the account's publishing limit, the
Instagram accounts of the user's Pages (the video upload is
meta_upload).

Verified 2026-11-01 (docs/decisions.md "TASK-141") on
https://developers.facebook.com/docs/instagram-platform/content-publishing:
GET /{ig-user}/content_publishing_limit
(fields=config,quota_usage) reports the API posts of the last 24 h.
"""

from typing import Any

import httpx

from clipforge.oauth import OAuthSession
from clipforge.publishers.base import PublishError
from clipforge.publishers.instagram_post import RETRYABLE_SUBCODES, publishing_limit
from clipforge.publishers.meta_graph import GRAPH, answer_json, graph_call

PLATFORM = "Instagram"
LIMIT_FIELDS = {"fields": "config,quota_usage"}


def graph(
    session: OAuthSession,
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a Graph API request of a reel post as the session's account."""
    return graph_call(
        session,
        method,
        url,
        "post the reel",
        PLATFORM,
        params=params,
        body=body,
        retryable_subcodes=RETRYABLE_SUBCODES,
    )


def limit_note(http: httpx.Client, auth: dict[str, str], ig_user: str) -> str:
    """Return the account's publishing limit use as a restriction (or why
    it is unknown) instead of failing the connection."""
    try:
        answer = answer_json(
            http.get(
                f"{GRAPH}/{ig_user}/content_publishing_limit",
                params=LIMIT_FIELDS,
                headers=auth,
            ),
            "report the publishing limit",
            PLATFORM,
        )
    except PublishError as exc:
        return exc.message
    limit = publishing_limit(answer)
    if limit is None:
        return "Instagram did not report the account's publishing limit."
    return f"API posts in the last 24 h: {limit[0]} of {limit[1]}."


def check_limit(session: OAuthSession, ig_user: str) -> None:
    """Raise a retryable PublishError if the account used up its API posts
    of the last 24 h (a limit Instagram cannot report now does not stop
    the post; a final refusal does)."""
    try:
        answer = graph(
            session,
            "GET",
            f"{GRAPH}/{ig_user}/content_publishing_limit",
            params=LIMIT_FIELDS,
        )
    except PublishError as exc:
        if not exc.retryable:
            raise
        return
    limit = publishing_limit(answer)
    if limit is not None and limit[0] >= limit[1]:
        raise PublishError(
            f"The account used its {limit[1]} Instagram API posts of the last "
            "24 h; the post is tried again later.",
            retryable=True,
        )


def instagram_accounts(pages: dict[str, Any]) -> list[dict[str, str]]:
    """Return the Instagram professional accounts linked to the Pages of a
    /me/accounts answer (id, username, name, avatar), sorted by username."""
    found: dict[str, dict[str, str]] = {}
    rows = pages.get("data")
    for page in rows if isinstance(rows, list) else []:
        account = (
            page.get("instagram_business_account") if isinstance(page, dict) else None
        )
        if not isinstance(account, dict) or not account.get("id"):
            continue
        account_id = str(account["id"])
        found[account_id] = {
            "id": account_id,
            "username": str(account.get("username") or account_id),
            "name": str(account.get("name") or ""),
            "avatar": str(account.get("profile_picture_url") or ""),
        }
    return sorted(found.values(), key=lambda a: a["username"].lower())
