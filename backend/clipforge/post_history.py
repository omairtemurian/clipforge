"""Posting history (SPEC-v2 3.10): the posts that went out, failed or were
skipped, newest first, with the links to the live posts (Post.url).

A post's moment in the history is when its latest upload started
(attempted_at), or its scheduled time if it was never tried (skipped).
"""

from sqlalchemy import Engine, func
from sqlmodel import Session, col, select

from clipforge.models import Post, PostStatus
from clipforge.social_rows import PostRow

HISTORY_STATUSES: tuple[PostStatus, ...] = ("published", "failed", "skipped")


def post_history(
    engine: Engine,
    *,
    status: PostStatus | None = None,
    account_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Post]:
    """Return the published, failed and skipped posts (only those in
    status, of account_id, if given; a status outside the history gives
    none), newest first, limit of them after offset."""
    statuses = [s for s in HISTORY_STATUSES if status in (None, s)]
    moment = func.coalesce(PostRow.attempted_at, PostRow.scheduled_at)
    query = (
        select(PostRow)
        .where(col(PostRow.status).in_(statuses))
        .order_by(moment.is_(None), moment.desc(), col(PostRow.id).desc())
        .offset(offset)
        .limit(limit)
    )
    if account_id is not None:
        query = query.where(col(PostRow.account_id) == account_id)
    with Session(engine) as session:
        return [row.to_model() for row in session.exec(query)]
