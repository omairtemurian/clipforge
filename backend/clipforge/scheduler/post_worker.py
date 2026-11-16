"""The posting worker (SPEC-v2 3.10): publishes the queued posts when they
are due, from the app's process, so nothing needs the UI open.

Every poll it takes the due posts (scheduler.post_queue.due_posts: queued,
their time reached, not held back) longest-due first and, for each:

1. Quota guard: if one upload would go over a daily quota of the platform
   (registry.quotas, e.g. YouTube's videos.insert per day), the post waits
   for the quota to reset; no attempt is counted.
2. Rate limits (scheduler.rate_limits): if its account or platform started
   too many uploads lately, the post waits until a start is free.
3. The publish run (publishers.publish.publish_post): published; failed;
   or queued again after the RetryPolicy's backoff (the last attempt
   fails it with the error).

A post that cannot be published yet (no source rights, no rendered video,
account disconnected, platform without its app keys) keeps its status and
says why in error; it is looked at again after the backoff's cap.

On start (recover), the posts left uploading by a stopped app fail
(post_queue.fail_interrupted): the platform may already have them. The
posts that came due while the app was off (post_queue.missed_posts: due
more than post_missed_grace_s before the start, never tried) are published
late by the polls, or skipped when post_missed_policy is "skip".
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine

from clipforge import config
from clipforge.models import Post, SocialPlatform
from clipforge.poller import Poller
from clipforge.posts import IllegalTransition, PostNotFound, PublishBlocked
from clipforge.publishers import registry
from clipforge.publishers.base import Publisher
from clipforge.publishers.publish import publish_post
from clipforge.scheduler import post_queue, rate_limits
from clipforge.scheduler.rate_limits import RateLimit
from clipforge.scheduler.retry import RetryPolicy
from clipforge.token_store import TokenStore

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PostWorker(Poller):
    """Publishes the due queued posts every interval seconds (default
    post_poll_s). now is the wall clock of due times, limits and backoff;
    clock (monotonic) paces the polls; publisher_for gives a platform's
    publisher (tests pass fakes)."""

    thread_name = "clipforge-post-worker"

    def __init__(
        self,
        engine: Engine,
        store: TokenStore,
        *,
        interval: float | None = None,
        retry: RetryPolicy | None = None,
        publisher_for: Callable[[SocialPlatform], Publisher] = registry.publisher,
        now: Callable[[], datetime] = _utcnow,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        poll_s = config.settings.post_poll_s if interval is None else interval
        super().__init__(interval=poll_s, clock=clock)
        self.engine = engine
        self.store = store
        self.retry = retry or RetryPolicy.from_settings()
        self.publisher_for = publisher_for
        self.now = now

    @classmethod
    def from_settings(cls, engine: Engine) -> "PostWorker":
        """Return a worker with the configured token store and settings."""
        return cls(engine, TokenStore.from_settings())

    def start(self) -> None:
        """Fail the uploads a stopped app left unfinished, then poll in a
        daemon thread until stop()."""
        self.recover()
        super().start()

    def recover(self) -> list[int]:
        """Fail the posts left uploading by a stopped app (their ids are
        returned), then apply the missed-while-offline policy."""
        failed = post_queue.fail_interrupted(self.engine)
        if failed:
            logger.warning("posts %s were uploading when the app stopped", failed)
        self.catch_up()
        return failed

    def catch_up(self) -> list[int]:
        """Skip the posts missed while the app was off when the setting
        post_missed_policy is "skip" (else the polls post them late);
        return the ids of the skipped posts."""
        settings = config.settings
        before = self.now() - timedelta(seconds=settings.post_missed_grace_s)
        missed = [post.id for post in post_queue.missed_posts(self.engine, before)]
        if not missed:
            return []
        if settings.post_missed_policy == "skip":
            skipped = post_queue.skip(self.engine, missed)
            logger.warning("posts %s were due while the app was off: skipped", skipped)
            return skipped
        logger.warning("posts %s were due while the app was off: posting late", missed)
        return []

    def poll(self) -> list[int]:
        """Try each due post once; return the ids of those whose upload
        ran (published, failed or queued for a retry)."""
        ran = []
        for post in post_queue.due_posts(self.engine, self.now()):
            if self._stop.is_set():
                break
            if self.run(post) is not None:
                ran.append(post.id)
        return ran

    def run(self, post: Post) -> Post | None:
        """Publish post unless a quota or rate limit holds it back or it
        cannot be published yet; return it after its upload, else None."""
        now = self.now()
        held = self.held_until(post, now)
        if held is not None:
            until, reason = held
            post_queue.defer(self.engine, post.id, until, reason)
            logger.info("post %d: held back until %s", post.id, until.isoformat())
            return None
        try:
            return publish_post(
                self.engine,
                post.id,
                self.store,
                self.publisher_for,
                retry=self.retry,
                now=self.now,
            )
        except (PublishBlocked, registry.PublisherUnavailable) as exc:
            post_queue.defer(self.engine, post.id, now + self.retry.cap, exc.message)
            logger.warning("post %d: not published yet: %s", post.id, exc.message)
        except (IllegalTransition, PostNotFound):
            logger.info("post %d: changed meanwhile; left as it is", post.id)
        return None

    def held_until(
        self, post: Post, now: datetime
    ) -> tuple[datetime, str | None] | None:
        """Return until when (and why, for a quota) a quota or rate limit
        holds post back at now, or None if it may be uploaded."""
        resets = [
            quota.next_reset(now)
            for quota, units in registry.quotas(post.platform)
            if not quota.allows(self.engine, units, now)
        ]
        if resets:
            reason = f"Waiting for the daily {post.platform} upload quota to reset."
            return max(resets), reason
        waits = [self._limited(rate_limits.platform_limits(post.platform), post, now)]
        if post.account_id is not None:
            account = rate_limits.account_limits(post.platform)
            waits.append(self._limited(account, post, now, post.account_id))
        held = [moment for moment in waits if moment is not None]
        return (max(held), None) if held else None

    def _limited(
        self,
        limits: list[RateLimit],
        post: Post,
        now: datetime,
        account_id: int | None = None,
    ) -> datetime | None:
        """Return until when limits hold the next upload of post's platform
        (of account_id, if given) back, or None."""
        if not limits:
            return None
        since = now - max(limit.window for limit in limits)
        if account_id is None:
            starts = post_queue.upload_starts(
                self.engine, since, platform=post.platform
            )
        else:
            starts = post_queue.upload_starts(self.engine, since, account_id=account_id)
        return rate_limits.wait_until(limits, starts, now)
