"""In-app notifications (SPEC-v2 3.17): messages for the owner, kept in the
notification table, shown in the app and also sent by email and to the
desktop if those channels are on (notification_delivery).

The events that make one, each called where the event happens:

    project_done      process.run_process_job, reprompt: a project's clips
                      are ready
    render_failed     clips.render_clip_row: a clip's video was not made
    posts_finished    posts.move / scheduler.post_queue: a post was published
                      or failed (its last failure: a retry is not an event)
    quota_warnings    jobs.run_claimed, after a job: a monthly usage cap is
                      quota_warn_percent % used, and again when it is used up

The event functions never raise: the job or post that caused the event must
go on. notify() writes the notification, then sends it to the other channels
(each with a timeout; a failure is logged).
"""

import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from functools import wraps
from typing import ParamSpec

from sqlalchemy import Engine, func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from clipforge import config, usage
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import (
    NOTIFICATION_BODY_MAX,
    NOTIFICATION_TITLE_MAX,
    Notification,
    NotificationKind,
    NotificationList,
)
from clipforge.notification_delivery import deliver
from clipforge.notification_rows import NotificationRow
from clipforge.social_rows import PostRow

logger = logging.getLogger(__name__)
P = ParamSpec("P")
LIST_LIMIT = 50
LIST_LIMIT_MAX = 200
SETTINGS_LINK = "/settings"


class NotificationNotFound(LookupError):
    """There is no notification with the given id."""


def _never_raises(event: Callable[P, None]) -> Callable[P, None]:
    """Wrap event so that a failure is logged, not raised."""

    @wraps(event)
    def guarded(*args: P.args, **kwargs: P.kwargs) -> None:
        try:
            event(*args, **kwargs)
        except Exception:
            logger.exception("could not make the notification of %s", event.__name__)

    return guarded


def _cut(text: str, limit: int) -> str:
    """Return text, shortened with an ellipsis if it is longer than limit."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def notify(
    engine: Engine,
    kind: NotificationKind,
    title: str,
    body: str = "",
    link: str | None = None,
    *,
    dedupe_key: str | None = None,
) -> Notification | None:
    """Add a notification and send it to the email and desktop channels that
    are on; return it. With a dedupe_key that a notification already has,
    nothing is added and None is returned."""
    row = NotificationRow(
        kind=kind,
        title=_cut(title, NOTIFICATION_TITLE_MAX),
        body=_cut(body, NOTIFICATION_BODY_MAX),
        link=link,
        dedupe_key=dedupe_key,
    )
    with Session(engine) as session:
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if dedupe_key is None:
                raise
            return None
        session.refresh(row)
        notification = row.to_model()
    deliver(config.settings, notification)
    return notification


def list_notifications(
    engine: Engine, *, unread_only: bool = False, limit: int = LIST_LIMIT
) -> NotificationList:
    """Return the newest notifications (at most limit, only the unread ones
    if unread_only) and the number of unread notifications in all."""
    query = select(NotificationRow).order_by(
        col(NotificationRow.created_at).desc(), col(NotificationRow.id).desc()
    )
    if unread_only:
        query = query.where(col(NotificationRow.read_at).is_(None))
    unread = select(func.count()).where(col(NotificationRow.read_at).is_(None))
    with Session(engine) as session:
        rows = session.exec(query.limit(max(1, min(limit, LIST_LIMIT_MAX)))).all()
        count = session.exec(unread.select_from(NotificationRow)).one()
        return NotificationList(
            items=[row.to_model() for row in rows], unread_count=count
        )


def mark_read(engine: Engine, notification_id: int) -> Notification:
    """Mark the notification read (if it is not already) and return it;
    NotificationNotFound if there is none."""
    with Session(engine) as session:
        row = session.get(NotificationRow, notification_id)
        if row is None:
            raise NotificationNotFound(f"notification {notification_id} does not exist")
        if row.read_at is None:
            row.read_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
        return row.to_model()


def mark_all_read(engine: Engine) -> int:
    """Mark every unread notification read; return how many there were."""
    statement = (
        update(NotificationRow)
        .where(col(NotificationRow.read_at).is_(None))
        .values(read_at=datetime.now(UTC))
    )
    with engine.begin() as conn:
        return conn.execute(statement).rowcount


def delete(engine: Engine, notification_id: int) -> None:
    """Delete the notification; NotificationNotFound if there is none."""
    with Session(engine) as session:
        row = session.get(NotificationRow, notification_id)
        if row is None:
            raise NotificationNotFound(f"notification {notification_id} does not exist")
        session.delete(row)
        session.commit()


@_never_raises
def project_done(engine: Engine, project_id: int) -> None:
    """Tell the owner that project project_id is done and how many clips it
    has."""
    with Session(engine) as session:
        project = session.get(ProjectRow, project_id)
        if project is None:
            return
        count = session.exec(
            select(func.count()).where(
                ClipRow.project_id == project_id,
                ClipRow.result_set == project.result_set,
            )
        ).one()
        title = project.title
    clips = f"{count} clip{'' if count == 1 else 's'}"
    notify(
        engine,
        "project_done",
        f"{title} is ready",
        f"{clips} found. Open the project to review them.",
        f"/projects/{project_id}",
    )


@_never_raises
def render_failed(engine: Engine, clip_id: int) -> None:
    """Tell the owner that the video of clip clip_id could not be made."""
    with Session(engine) as session:
        clip = session.get(ClipRow, clip_id)
        if clip is None:
            return
        title = clip.title
    notify(
        engine,
        "render_failed",
        f"Render failed: {title}",
        "The clip's video was not made. Open the clip, then render it again; "
        "the job log has the reason.",
        f"/clips/{clip_id}",
    )


@_never_raises
def posts_finished(engine: Engine, post_ids: Iterable[int]) -> None:
    """Tell the owner of each post that now is published or failed (a post in
    another status says nothing)."""
    for post_id in post_ids:
        with Session(engine) as session:
            post = session.get(PostRow, post_id)
            if post is None or post.status not in ("published", "failed"):
                continue
            clip = session.get(ClipRow, post.clip_id)
            clip_title = clip.title if clip is not None else f"clip {post.clip_id}"
            platform, status, error, url = (
                post.platform,
                post.status,
                post.error,
                post.url,
            )
        if status == "published":
            notify(
                engine,
                "post_published",
                f"Posted to {platform}: {clip_title}",
                url or "",
                "/post-history",
            )
        else:
            notify(
                engine,
                "post_failed",
                f"Post to {platform} failed: {clip_title}",
                error or "The upload failed.",
                "/post-history",
            )


@_never_raises
def quota_warnings(engine: Engine, now: datetime | None = None) -> None:
    """Warn the owner of each monthly usage cap that is quota_warn_percent %
    used, and again when it is used up; a month gets each message once."""
    cfg = config.settings
    if not usage.caps_of(cfg):
        return
    moment = usage.utc_now() if now is None else now
    summary = usage.month_summary(engine, moment.date(), cfg)
    for item in summary.kinds:
        if item.cap is None:
            continue
        used = (
            f"{usage.describe(item.kind, item.units)} of "
            f"{usage.describe(item.kind, item.cap)} in {summary.month}."
        )
        if item.exceeded:
            level, title = "used_up", "Monthly cap used up"
            body = f"{used} New jobs are refused until next month or the cap is raised."
        elif item.units >= item.cap * cfg.quota_warn_percent / 100:
            level, title = "warning", "Monthly cap nearly used up"
            body = f"{used} Raise the cap in Settings to keep going."
        else:
            continue
        notify(
            engine,
            "quota_warning",
            title,
            body,
            SETTINGS_LINK,
            dedupe_key=f"quota:{summary.month}:{item.kind}:{level}",
        )
