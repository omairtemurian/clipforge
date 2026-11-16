"""The publish run of one queued post (SPEC-v2 3.10): the checks before the
upload, the platform's publisher, and the post's status around it.

    queued -> uploading -> published            (upload worked)
                        -> queued               (PublishError, retryable)
                        -> failed               (any other failure)

PublishBlocked (status unchanged) when the project of the clip has no
source rights (SPEC-v2 1.6), the clip has no rendered video or the post's
account was disconnected; PublisherUnavailable (registry) when the
platform cannot be used. The posting worker (scheduler.post_worker)
decides when to run it. A retryable failure holds the post back
(next_attempt_at) by the RetryPolicy's backoff, or until the quota resets
(QuotaExceeded: the attempt is not counted, nothing was sent); the
policy's last attempt fails it for good. The upload runs in a
usage.recording() context of the clip's project, so publishers meter and
guard their API quotas (publishers.quota).
"""

import dataclasses
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import posts, social_accounts, usage
from clipforge.asset_rows import AssetRow
from clipforge.db import ClipRow
from clipforge.models import Clip, Post, SocialPlatform
from clipforge.oauth import OAuthError
from clipforge.posts import PublishBlocked
from clipforge.publishers import registry
from clipforge.publishers.base import Publisher, PublishError, Upload
from clipforge.publishers.quota import QuotaExceeded
from clipforge.scheduler.retry import RetryPolicy
from clipforge.token_store import TokenStore

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def publish_post(
    engine: Engine,
    post_id: int,
    store: TokenStore,
    publisher_for: Callable[[SocialPlatform], Publisher] = registry.publisher,
    *,
    retry: RetryPolicy | None = None,
    now: Callable[[], datetime] = _utcnow,
) -> Post:
    """Upload the queued post with its platform's publisher and return it
    in its new status (published, failed, or queued again for a retry).
    retry defaults to RetryPolicy.from_settings(); now is the clock."""
    post = posts.get_post(engine, post_id)
    if post.status != "queued":
        raise posts.IllegalTransition(post_id, post.status, "uploading")
    posts.require_rights(engine, post.clip_id)
    upload = upload_of(engine, post)
    if post.account_id is None:
        raise PublishBlocked(
            "account_missing", "The account of this post was disconnected."
        )
    account = social_accounts.get_account(engine, post.account_id)
    upload = dataclasses.replace(upload, account_external_id=account.external_id)
    publisher = publisher_for(post.platform)
    attempt = post.attempts + 1
    posts.move(
        engine,
        post_id,
        "uploading",
        attempts=attempt,
        error=None,
        attempted_at=now(),
        next_attempt_at=None,
    )
    try:
        session = publisher.session(store, account.token_ref)
        with usage.recording(engine, upload.clip.project_id):
            result = publisher.upload(session, upload)
    except QuotaExceeded as exc:
        logger.info("post %s: waits for the quota: %s", post_id, exc)
        return posts.move(
            engine,
            post_id,
            "queued",
            error=exc.message,
            attempts=post.attempts,
            attempted_at=post.attempted_at,
            next_attempt_at=exc.retry_at,
        )
    except PublishError as exc:
        return _failed_upload(engine, post_id, attempt, exc, retry, now())
    except OAuthError as exc:
        logger.info("post %s: sign-in failed: %s", post_id, exc.code)
        return posts.move(engine, post_id, "failed", error=exc.message)
    except Exception as exc:
        logger.exception("post %s: the upload raised", post_id)
        return posts.move(engine, post_id, "failed", error=f"Upload error: {exc}")
    return posts.move(
        engine,
        post_id,
        "published",
        external_post_id=result.external_post_id,
        url=result.url,
        error=None,
    )


def _failed_upload(
    engine: Engine,
    post_id: int,
    attempt: int,
    exc: PublishError,
    retry: RetryPolicy | None,
    moment: datetime,
) -> Post:
    """Queue the post again after the backoff if exc is retryable and
    attempts are left; fail it otherwise."""
    policy = retry or RetryPolicy.from_settings()
    if exc.retryable and not policy.gives_up(attempt):
        logger.info("post %s: attempt %d failed, retried: %s", post_id, attempt, exc)
        return posts.move(
            engine,
            post_id,
            "queued",
            error=exc.message,
            next_attempt_at=moment + policy.delay(attempt),
        )
    message = exc.message
    if exc.retryable:
        message = f"{message} (gave up after {attempt} attempts)"
    logger.info("post %s: upload failed: %s", post_id, message)
    return posts.move(engine, post_id, "failed", error=message)


def upload_of(engine: Engine, post: Post) -> Upload:
    """Return what the post uploads; PublishBlocked clip_not_rendered if the
    clip's video is missing."""
    with Session(engine) as session:
        clip_row = session.get(ClipRow, post.clip_id)
        if clip_row is None:
            raise posts.PostNotFound(f"clip {post.clip_id} does not exist")
        clip = clip_row.to_model()
        thumbnail = None
        if post.thumbnail_asset_id is not None:
            asset = session.get(AssetRow, post.thumbnail_asset_id)
            thumbnail = Path(asset.path) if asset is not None else None
    return Upload(post=post, clip=clip, video=rendered_video(clip), thumbnail=thumbnail)


def rendered_video(clip: Clip) -> Path:
    """Return the clip's rendered video; PublishBlocked clip_not_rendered if
    it is missing."""
    video = Path(clip.output_path) if clip.output_path else None
    if video is None or not video.is_file():
        raise PublishBlocked(
            "clip_not_rendered", f"Render clip {clip.id} before publishing it."
        )
    return video
