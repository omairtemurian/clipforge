"""The payloads of the webhook events and the places that raise them
(SPEC-v2 3.14): each function reads what the event is about and calls
webhooks.emit, which queues the deliveries (it never raises).

    project.completed   process.run_process_job, when the project is done
    clip.rendered       clips.render_clip_row, when a clip's video is made
    post.published      posts.move / scheduler.post_queue.fail_interrupted,
    post.failed         when a post reaches published / failed (its last
                        failure: a retry is not an event)

The "data" of every event holds ids and the API paths of what it is about
(the API's `/api/...` paths, not file paths on the disk); a client fetches
the details with the API (docs/automation.md).
"""

import logging
from collections.abc import Callable, Iterable
from functools import wraps
from typing import ParamSpec

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge import webhooks
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import WebhookEvent
from clipforge.social_rows import PostRow

logger = logging.getLogger(__name__)
P = ParamSpec("P")


def _never_raises(raise_event: Callable[P, None]) -> Callable[P, None]:
    """Wrap raise_event so that a failure is logged, not raised: the job or
    post that caused the event must go on."""

    @wraps(raise_event)
    def guarded(*args: P.args, **kwargs: P.kwargs) -> None:
        try:
            raise_event(*args, **kwargs)
        except Exception:
            logger.exception("could not raise the webhook event")

    return guarded


@_never_raises
def project_completed(engine: Engine, project_id: int) -> None:
    """Raise project.completed for the finished project and its clips."""
    with Session(engine) as session:
        project = session.get(ProjectRow, project_id)
        if project is None:
            return
        clips = session.exec(
            select(ClipRow.id, ClipRow.title)
            .where(
                ClipRow.project_id == project_id,
                ClipRow.result_set == project.result_set,
            )
            .order_by(col(ClipRow.id))
        ).all()
        data = {
            "project": {
                "id": project_id,
                "title": project.title,
                "source_url": project.source_url,
                "duration": project.duration,
                "created_at": project.created_at.isoformat(),
                "path": f"/api/projects/{project_id}",
            },
            "clips": [{"id": clip_id, "title": title} for clip_id, title in clips],
        }
    webhooks.emit(engine, "project.completed", data)


@_never_raises
def clip_rendered(engine: Engine, clip_id: int) -> None:
    """Raise clip.rendered for the clip whose video was just made."""
    with Session(engine) as session:
        clip = session.get(ClipRow, clip_id)
        if clip is None:
            return
        data = {
            "clip": {
                "id": clip_id,
                "project_id": clip.project_id,
                "title": clip.title,
                "overall_score": clip.scores.overall,
                "download_path": f"/api/clips/{clip_id}/download",
                "srt_path": f"/api/clips/{clip_id}/srt",
            }
        }
    webhooks.emit(engine, "clip.rendered", data)


@_never_raises
def posts_finished(engine: Engine, post_ids: Iterable[int]) -> None:
    """Raise post.published or post.failed for each post that now has that
    status (a post in another status raises nothing)."""
    for post_id in post_ids:
        with Session(engine) as session:
            post = session.get(PostRow, post_id)
            if post is None or post.status not in ("published", "failed"):
                continue
            data = {
                "post": {
                    "id": post_id,
                    "clip_id": post.clip_id,
                    "platform": post.platform,
                    "status": post.status,
                    "url": post.url,
                    "external_post_id": post.external_post_id,
                    "error": post.error,
                    "attempts": post.attempts,
                }
            }
            event: WebhookEvent = (
                "post.published" if post.status == "published" else "post.failed"
            )
        webhooks.emit(engine, event, data)
