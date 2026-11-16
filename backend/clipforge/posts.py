"""Posts of clips to social accounts (SPEC-v2 3.10, 4): the post status
machine and the database operations that the publish endpoints, the
scheduler and the posting worker share.

    draft -> queued -> uploading -> published | failed
    draft | queued | failed -> canceled
    queued -> skipped (missed while the app was off) -> queued | canceled

TRANSITIONS lists every legal move; move() refuses the others with
IllegalTransition. Besides the main line a queued post may go back to
draft (unscheduled), an upload that failed for a passing reason goes back
to queued (retried) and a failed post may be queued again. An upload that
has started cannot be canceled (the platform may already have the video).

Publishing is blocked (PublishBlocked source_rights_missing) while the
project of the clip has no source rights (SPEC-v2 1.6): queue_post() and
the publish run (clipforge.publishers.publish) check it.

Only a draft or queued post (EDITABLE) may be edited, rescheduled or
canceled through the API (update_post, cancel_post: PostLocked otherwise).
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, update
from sqlmodel import Session, col, select

from clipforge import notifications, rights, webhook_events
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import Post, PostStatus
from clipforge.social_rows import PostRow, SocialAccountRow

TRANSITIONS: dict[PostStatus, frozenset[PostStatus]] = {
    "draft": frozenset({"queued", "canceled"}),
    "queued": frozenset({"draft", "uploading", "canceled", "skipped"}),
    "uploading": frozenset({"published", "failed", "queued"}),
    "failed": frozenset({"queued", "canceled"}),
    "published": frozenset(),
    "canceled": frozenset(),
    "skipped": frozenset({"queued", "canceled"}),
}
# The fields that a move may change besides the status.
MOVE_FIELDS = frozenset(
    {
        "scheduled_at",
        "error",
        "external_post_id",
        "url",
        "attempts",
        "attempted_at",
        "next_attempt_at",
    }
)
EDITABLE: frozenset[PostStatus] = frozenset({"draft", "queued"})
# The fields that update_post may change.
EDIT_FIELDS = frozenset({"payload", "scheduled_at", "thumbnail_asset_id"})


class IllegalTransition(Exception):
    """A post cannot move from its status to the one asked for."""

    def __init__(self, post_id: int, old: PostStatus, new: PostStatus) -> None:
        super().__init__(f"post {post_id} cannot go from {old} to {new}")
        self.post_id = post_id
        self.old = old
        self.new = new


class PublishBlocked(Exception):
    """A post may not be published yet; code is a short API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PostNotFound(LookupError):
    """There is no such post, clip or account."""


class PostLocked(Exception):
    """The post is past draft and queued: it cannot change any more."""

    def __init__(self, post_id: int, status: PostStatus) -> None:
        super().__init__(
            f"post {post_id} is {status}; only draft and queued posts can change"
        )
        self.post_id = post_id
        self.status = status


def can_move(old: PostStatus, new: PostStatus) -> bool:
    """Return whether a post may go from old to new."""
    return new in TRANSITIONS[old]


def create_post(
    engine: Engine,
    *,
    clip_id: int,
    account_id: int,
    payload: dict[str, Any],
    scheduled_at: datetime | None = None,
    thumbnail_asset_id: int | None = None,
) -> Post:
    """Add a draft post of clip_id to account_id (on the account's
    platform); PostNotFound if the clip or account does not exist."""
    with Session(engine) as session:
        if session.get(ClipRow, clip_id) is None:
            raise PostNotFound(f"clip {clip_id} does not exist")
        account = session.get(SocialAccountRow, account_id)
        if account is None:
            raise PostNotFound(f"account {account_id} does not exist")
        row = PostRow(
            clip_id=clip_id,
            account_id=account_id,
            platform=account.platform,
            payload=payload,
            scheduled_at=scheduled_at,
            thumbnail_asset_id=thumbnail_asset_id,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def get_post(engine: Engine, post_id: int) -> Post:
    """Return the post; PostNotFound if there is none."""
    with Session(engine) as session:
        row = session.get(PostRow, post_id)
        if row is None:
            raise PostNotFound(f"post {post_id} does not exist")
        return row.to_model()


def move(engine: Engine, post_id: int, new: PostStatus, **changes: Any) -> Post:
    """Move the post to status new and set changes (MOVE_FIELDS) in one
    conditional UPDATE; IllegalTransition if the move is not legal from the
    post's status (also when another writer changed it meanwhile)."""
    unknown = set(changes) - MOVE_FIELDS
    if unknown:
        raise ValueError(f"a move cannot change {sorted(unknown)}")
    old = get_post(engine, post_id).status
    if not can_move(old, new):
        raise IllegalTransition(post_id, old, new)
    statement = (
        update(PostRow)
        .where(col(PostRow.id) == post_id, col(PostRow.status) == old)
        .values(status=new, **changes)
    )
    with engine.begin() as conn:
        moved = conn.execute(statement).rowcount
    if moved != 1:
        raise IllegalTransition(post_id, get_post(engine, post_id).status, new)
    webhook_events.posts_finished(engine, [post_id])
    notifications.posts_finished(engine, [post_id])
    return get_post(engine, post_id)


def require_rights(engine: Engine, clip_id: int) -> None:
    """PublishBlocked source_rights_missing unless the project of clip_id
    has its source rights set; PostNotFound if the clip does not exist."""
    with Session(engine) as session:
        clip = session.get(ClipRow, clip_id)
        project = session.get(ProjectRow, clip.project_id) if clip else None
        if project is None:
            raise PostNotFound(f"clip {clip_id} does not exist")
        if not rights.rights_ok(project.to_model()):
            raise PublishBlocked(
                "source_rights_missing",
                f"Set the source rights of project {project.id} "
                "(why you may use its video) before publishing its clips.",
            )


def queue_post(
    engine: Engine, post_id: int, scheduled_at: datetime | None = None
) -> Post:
    """Queue the post to be published at scheduled_at (None: as soon as
    possible), with a fresh count of upload attempts; PublishBlocked while
    its project has no source rights."""
    require_rights(engine, get_post(engine, post_id).clip_id)
    return move(
        engine,
        post_id,
        "queued",
        scheduled_at=scheduled_at,
        error=None,
        attempts=0,
        next_attempt_at=None,
    )


def list_posts(
    engine: Engine,
    *,
    clip_id: int | None = None,
    account_id: int | None = None,
    status: PostStatus | None = None,
) -> list[Post]:
    """Return the posts (of clip_id, account_id and in status, if given),
    oldest first."""
    query = select(PostRow).order_by(col(PostRow.id))
    if clip_id is not None:
        query = query.where(col(PostRow.clip_id) == clip_id)
    if account_id is not None:
        query = query.where(col(PostRow.account_id) == account_id)
    if status is not None:
        query = query.where(col(PostRow.status) == status)
    with Session(engine) as session:
        return [row.to_model() for row in session.exec(query)]


def update_post(engine: Engine, post_id: int, **changes: Any) -> Post:
    """Set changes (EDIT_FIELDS) of a draft or queued post in one
    conditional UPDATE; PostLocked if it is in another status (also when
    another writer moved it meanwhile)."""
    unknown = set(changes) - EDIT_FIELDS
    if unknown:
        raise ValueError(f"an update cannot change {sorted(unknown)}")
    post = get_post(engine, post_id)
    if post.status not in EDITABLE:
        raise PostLocked(post_id, post.status)
    if not changes:
        return post
    statement = (
        update(PostRow)
        .where(col(PostRow.id) == post_id, col(PostRow.status).in_(EDITABLE))
        .values(**changes)
    )
    with engine.begin() as conn:
        updated = conn.execute(statement).rowcount
    if updated != 1:
        raise PostLocked(post_id, get_post(engine, post_id).status)
    return get_post(engine, post_id)


def cancel_post(engine: Engine, post_id: int) -> Post:
    """Cancel a draft or queued post; PostLocked in any other status."""
    post = get_post(engine, post_id)
    if post.status not in EDITABLE:
        raise PostLocked(post_id, post.status)
    try:
        return move(engine, post_id, "canceled")
    except IllegalTransition as exc:
        raise PostLocked(post_id, exc.old) from exc


def scheduled_times(
    engine: Engine, account_ids: Iterable[int]
) -> list[tuple[int, datetime]]:
    """Return (account_id, scheduled_at) of the draft and queued posts of
    the accounts that have a time: the slots they already hold."""
    ids = list(account_ids)
    query = select(PostRow.account_id, PostRow.scheduled_at).where(
        col(PostRow.account_id).in_(ids),
        col(PostRow.status).in_(EDITABLE),
        col(PostRow.scheduled_at).is_not(None),
    )
    with Session(engine) as session:
        return [
            (account_id, scheduled_at)
            for account_id, scheduled_at in session.exec(query)
            if account_id is not None and scheduled_at is not None
        ]
