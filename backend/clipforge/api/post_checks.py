"""The checks before a post may be queued or published now (SPEC-v2 3.10,
1.6, 3.18) and the publish-now run, shared by the post endpoints.

Each failed check answers 409 with its own code: source_rights_missing,
permission_missing, campaign_rules_failed (the failed rules), clip_not_rendered,
account_missing or post_not_ready (e.g. no TikTok privacy chosen).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import post_payload, posts
from clipforge.api.campaign_rules import require_campaign_rules
from clipforge.api.campaigns import require_campaign_permission
from clipforge.api.deps import clip_row
from clipforge.api.errors import ApiError
from clipforge.asset_rows import AssetRow
from clipforge.models import Post, SocialPlatform
from clipforge.posts import PublishBlocked
from clipforge.publishers import publish, registry
from clipforge.token_store import TokenStore
from clipforge.watch.times import as_utc

logger = logging.getLogger(__name__)


def check_publishable(engine: Engine, post: Post) -> None:
    """Raise the 409 of the first check that post fails before it may be
    queued or published (check_target)."""
    check_target(engine, post.clip_id, post.platform, post.payload, post.account_id)


def check_target(
    engine: Engine,
    clip_id: int,
    platform: SocialPlatform,
    payload: dict[str, Any],
    account_id: int | None,
) -> None:
    """Raise the 409 of the first check that a post of clip_id on platform
    fails before it may be queued or published: source rights, the
    campaign's permission and rules on the platform, a rendered video, an
    account, and the platform's required choices (payload)."""
    posts.require_rights(engine, clip_id)
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
    require_campaign_permission(clip.project_id, engine)
    require_campaign_rules(clip_id, engine, platform)
    publish.rendered_video(clip)
    if account_id is None:
        raise PublishBlocked(
            "account_missing", "The account of this post was disconnected."
        )
    problem = post_payload.ready_problem(platform, payload)
    if problem:
        raise ApiError(409, "post_not_ready", problem)


def check_platform(post: Post) -> None:
    """Raise the API error of a platform that cannot publish now (501 no
    publisher, 412 its developer app is not configured)."""
    check_platform_name(post.platform)


def check_platform_name(platform: SocialPlatform) -> None:
    """Raise check_platform's API error for platform."""
    try:
        registry.publisher(platform)
    except registry.PublisherUnavailable as exc:
        raise ApiError(exc.status, exc.code, exc.message) from exc


def future_time(moment: datetime | None) -> datetime | None:
    """Return moment as UTC; 422 if it is not in the future (None: none)."""
    if moment is None:
        return None
    moment = as_utc(moment)
    if moment <= datetime.now(UTC):
        raise ApiError(422, "validation_error", "scheduled_at: pick a future time")
    return moment


def check_thumbnail(engine: Engine, asset_id: int | None) -> None:
    """422 if the thumbnail asset does not exist."""
    if asset_id is None:
        return
    with Session(engine) as session:
        if session.get(AssetRow, asset_id) is None:
            raise ApiError(
                422, "validation_error", f"thumbnail_asset_id: no asset {asset_id}"
            )


def run_publish(engine: Engine, post_id: int) -> None:
    """Publish the queued post now (background task of publish now); a
    refusal leaves it as the publish run put it, and is logged."""
    try:
        publish.publish_post(engine, post_id, TokenStore.from_settings())
    except (
        PublishBlocked,
        registry.PublisherUnavailable,
        posts.IllegalTransition,
        posts.PostNotFound,
    ) as exc:
        logger.warning("post %d: not published now: %s", post_id, exc)
