"""The database side of the posting worker (SPEC-v2 3.10): which queued
posts are due, holding a post back, the upload starts that rate limits
count, the uploads that a stopped app left unfinished and the posts that
came due while it was off.

Times are compared as UTC (SQLite keeps them without a zone).
"""

from datetime import datetime

from sqlalchemy import Engine, and_, func, or_, update
from sqlmodel import Session, col, select

from clipforge import notifications, posts, webhook_events
from clipforge.models import Post, SocialPlatform
from clipforge.social_rows import PostRow
from clipforge.watch.times import as_utc

# What a post that was uploading when the app stopped says: the platform
# may already have the video, so it is never sent again on its own.
INTERRUPTED = (
    "The app stopped during the upload. Check the account on the platform "
    "before posting it again."
)
# What a post skipped by the missed-while-offline policy says.
SKIPPED = (
    "Skipped: it was due while ClipForge was off (Settings > Posting). "
    "Post it now from its details if you still want it out."
)


def due_posts(engine: Engine, now: datetime) -> list[Post]:
    """Return the queued posts due at now (no time or a time not after now)
    and not held back past now, the longest-due first."""
    moment = as_utc(now)
    due_at = func.coalesce(PostRow.next_attempt_at, PostRow.scheduled_at)
    query = (
        select(PostRow)
        .where(
            col(PostRow.status) == "queued",
            or_(
                col(PostRow.scheduled_at).is_(None), col(PostRow.scheduled_at) <= moment
            ),
            or_(
                col(PostRow.next_attempt_at).is_(None),
                col(PostRow.next_attempt_at) <= moment,
            ),
        )
        .order_by(due_at.is_not(None), due_at, col(PostRow.id))
    )
    with Session(engine) as session:
        return [row.to_model() for row in session.exec(query)]


def defer(
    engine: Engine, post_id: int, until: datetime, error: str | None = None
) -> bool:
    """Hold the queued post back until then, saying why in error if given;
    return False if it is no longer queued."""
    values: dict[str, object] = {"next_attempt_at": as_utc(until)}
    if error is not None:
        values["error"] = error
    statement = (
        update(PostRow)
        .where(col(PostRow.id) == post_id, col(PostRow.status) == "queued")
        .values(**values)
    )
    with engine.begin() as conn:
        return bool(conn.execute(statement).rowcount == 1)


def upload_starts(
    engine: Engine,
    since: datetime,
    *,
    account_id: int | None = None,
    platform: SocialPlatform | None = None,
) -> list[datetime]:
    """Return the latest upload start of each post (of account_id, of
    platform, if given) that started after since."""
    query = select(PostRow.attempted_at).where(
        col(PostRow.attempted_at).is_not(None),
        col(PostRow.attempted_at) > as_utc(since),
    )
    if account_id is not None:
        query = query.where(col(PostRow.account_id) == account_id)
    if platform is not None:
        query = query.where(col(PostRow.platform) == platform)
    with Session(engine) as session:
        return [as_utc(start) for start in session.exec(query) if start is not None]


def fail_interrupted(engine: Engine) -> list[int]:
    """Fail the posts left uploading by a stopped app (INTERRUPTED) and
    return their ids; call it before anything uploads."""
    with Session(engine) as session:
        ids = list(
            session.exec(select(PostRow.id).where(col(PostRow.status) == "uploading"))
        )
    found = [post_id for post_id in ids if post_id is not None]
    if found:
        statement = (
            update(PostRow)
            .where(and_(col(PostRow.id).in_(found), col(PostRow.status) == "uploading"))
            .values(status="failed", error=INTERRUPTED, next_attempt_at=None)
        )
        with engine.begin() as conn:
            conn.execute(statement)
        webhook_events.posts_finished(engine, found)
        notifications.posts_finished(engine, found)
    return found


def missed_posts(engine: Engine, before: datetime) -> list[Post]:
    """Return the queued posts missed while the app was off: their time is
    not after before, no upload of theirs started since they were queued
    and no running worker held them back (next_attempt_at unset); the
    earliest first."""
    query = (
        select(PostRow)
        .where(
            col(PostRow.status) == "queued",
            col(PostRow.attempts) == 0,
            col(PostRow.next_attempt_at).is_(None),
            col(PostRow.scheduled_at).is_not(None),
            col(PostRow.scheduled_at) <= as_utc(before),
        )
        .order_by(col(PostRow.scheduled_at), col(PostRow.id))
    )
    with Session(engine) as session:
        return [row.to_model() for row in session.exec(query)]


def skip(engine: Engine, post_ids: list[int]) -> list[int]:
    """Move the queued posts of post_ids to skipped (SKIPPED); return the
    ids of those that were still queued."""
    skipped = []
    for post_id in post_ids:
        try:
            posts.move(engine, post_id, "skipped", error=SKIPPED)
        except posts.IllegalTransition:
            continue
        skipped.append(post_id)
    return skipped
