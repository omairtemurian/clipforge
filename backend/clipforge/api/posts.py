"""Post endpoints (SPEC-v2 3.10): drafts of a clip for several accounts with
per-platform text, publish now, schedule, reschedule, cancel and the bulk
scheduler.

    GET   /posts                 ?clip_id=&account_id=&status= -> [Post]
    GET   /posts/history         ?status=&account_id=&limit=&offset= -> [Post]
    GET   /posts/{id}            -> Post
    POST  /clips/{id}/posts      PostCreate -> [Post] (drafts, 201)
    PATCH /posts/{id}            PostPatch -> Post (edit / reschedule)
    POST  /posts/{id}/queue      PostQueue -> Post (human only)
    POST  /posts/{id}/publish    -> Post, queued; uploads now (human only)
    POST  /posts/{id}/cancel     -> Post
    POST  /posts/bulk-schedule   BulkSchedule -> [Post] (201)

AI agents (API key, MCP) may make drafts and draft schedules; queuing and
publishing are the owner's (403 human_only, api.deps.require_human), and
so is changing a queued post. Edit, reschedule and cancel only work on
draft and queued posts (409 post_locked). Queue and publish check the
post first (api.post_checks: rights, campaign, render, platform choices).
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import post_payload, post_schedule, posts, social_accounts
from clipforge.api import post_checks
from clipforge.api.deps import clip_row, get_engine, require_human
from clipforge.api.errors import ApiError, not_found
from clipforge.models import (
    BulkSchedule,
    Clip,
    Post,
    PostCreate,
    PostPatch,
    PostQueue,
    PostStatus,
    PostText,
    SocialAccount,
    SocialPlatform,
)
from clipforge.post_history import post_history
from clipforge.post_tags import required_hashtags
from clipforge.scheduler.slots import NoFreeSlot

router = APIRouter()

EngineDep = Annotated[Engine, Depends(get_engine)]
Payload = dict[str, Any]


@router.get("/posts")
def list_posts(
    engine: EngineDep,
    clip_id: int | None = None,
    account_id: int | None = None,
    status: PostStatus | None = None,
) -> list[Post]:
    """Return the posts (of a clip, an account, in a status), oldest first."""
    return posts.list_posts(
        engine, clip_id=clip_id, account_id=account_id, status=status
    )


@router.get("/posts/history")
def list_post_history(
    engine: EngineDep,
    status: PostStatus | None = None,
    account_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Post]:
    """Return the posting history: published (with the link to the live
    post), failed and skipped posts, newest first."""
    return post_history(
        engine, status=status, account_id=account_id, limit=limit, offset=offset
    )


@router.get("/posts/{post_id}")
def get_post(post_id: int, engine: EngineDep) -> Post:
    """Return one post."""
    return _post(engine, post_id)


@router.post("/clips/{clip_id}/posts", status_code=201)
def create_posts(clip_id: int, body: PostCreate, engine: EngineDep) -> list[Post]:
    """Save a draft post of the clip for each target account, with the
    target's text made into its platform's payload (422 if the platform
    would refuse it; 404 for an unknown clip or account)."""
    clip = _clip(engine, clip_id)
    scheduled_at = post_checks.future_time(body.scheduled_at)
    post_checks.check_thumbnail(engine, body.thumbnail_asset_id)
    seen: set[int] = set()
    payloads = []
    for target in body.targets:
        if target.account_id in seen:
            raise ApiError(
                422, "validation_error", f"account {target.account_id} is listed twice"
            )
        seen.add(target.account_id)
        account = _account(engine, target.account_id)
        payloads.append(_payload(engine, account, target.text, clip))
    return [
        posts.create_post(
            engine,
            clip_id=clip_id,
            account_id=target.account_id,
            payload=payload,
            scheduled_at=scheduled_at,
            thumbnail_asset_id=body.thumbnail_asset_id,
        )
        for target, payload in zip(body.targets, payloads, strict=True)
    ]


@router.patch("/posts/{post_id}")
def patch_post(
    post_id: int, body: PostPatch, request: Request, engine: EngineDep
) -> Post:
    """Change the text, time (reschedule) or thumbnail of a draft or queued
    post; 409 post_locked in any other status. A queued post is the
    owner's to change (403 human_only for agents)."""
    post = _post(engine, post_id)
    if post.status == "queued":
        require_human(request)
    changes: Payload = {}
    if body.text is not None:
        clip = _clip(engine, post.clip_id)
        account = None if post.account_id is None else _account(engine, post.account_id)
        changes["payload"] = _payload(engine, account, body.text, clip, post.platform)
    if "scheduled_at" in body.model_fields_set:
        changes["scheduled_at"] = post_checks.future_time(body.scheduled_at)
    if "thumbnail_asset_id" in body.model_fields_set:
        post_checks.check_thumbnail(engine, body.thumbnail_asset_id)
        changes["thumbnail_asset_id"] = body.thumbnail_asset_id
    return _locked(lambda: posts.update_post(engine, post_id, **changes))


@router.post("/posts/{post_id}/queue", dependencies=[Depends(require_human)])
def queue_post(post_id: int, body: PostQueue, engine: EngineDep) -> Post:
    """Queue a draft (or failed) post to be published at body's
    scheduled_at (left out: the post's own; null: as soon as possible),
    after the publish checks."""
    post = _post(engine, post_id)
    moment = (
        body.scheduled_at
        if "scheduled_at" in body.model_fields_set
        else post.scheduled_at
    )
    scheduled_at = post_checks.future_time(moment)
    post_checks.check_publishable(engine, post)
    return _moved(lambda: posts.queue_post(engine, post_id, scheduled_at))


@router.post("/posts/{post_id}/publish", dependencies=[Depends(require_human)])
def publish_now(post_id: int, engine: EngineDep, background: BackgroundTasks) -> Post:
    """Publish a draft, queued or failed post now: it is queued for as soon
    as possible and uploaded right after this answer (its status then
    moves to published, or failed, or stays queued for a retry)."""
    post = _post(engine, post_id)
    post_checks.check_publishable(engine, post)
    post_checks.check_platform(post)
    if post.status == "queued":
        queued = _locked(lambda: posts.update_post(engine, post_id, scheduled_at=None))
    else:
        queued = _moved(lambda: posts.queue_post(engine, post_id, None))
    background.add_task(post_checks.run_publish, engine, post_id)
    return queued


@router.post("/posts/{post_id}/cancel")
def cancel_post(post_id: int, engine: EngineDep) -> Post:
    """Cancel a draft or queued post; 409 post_locked otherwise."""
    _post(engine, post_id)
    return _locked(lambda: posts.cancel_post(engine, post_id))


@router.post("/posts/bulk-schedule", status_code=201)
def bulk_schedule(
    body: BulkSchedule, request: Request, engine: EngineDep
) -> list[Post]:
    """Post every clip to every target account, each in the account's next
    free slot of the rules, as drafts with their time, or queued with
    body.queue (human only; each post passes the publish checks first).
    409 no_free_slot when they do not fit in the next two years."""
    if body.queue:
        require_human(request)
    before_save = _publish_checks(engine) if body.queue else None
    try:
        created = post_schedule.bulk_schedule(
            engine,
            body,
            lambda clip_id: _clip(engine, clip_id),
            datetime.now(UTC),
            before_save,
        )
    except posts.PostNotFound as exc:
        raise ApiError(404, "not_found", str(exc)) from exc
    except post_payload.PayloadInvalid as exc:
        raise ApiError(422, "validation_error", exc.message) from exc
    except NoFreeSlot as exc:
        raise ApiError(
            409, "no_free_slot", "The posts do not fit in the slots."
        ) from exc
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    if not body.queue:
        return created
    return [posts.queue_post(engine, post.id, post.scheduled_at) for post in created]


def _publish_checks(engine: Engine) -> post_schedule.BeforeSave:
    """Return the bulk scheduler's check of each post before it is queued."""

    def check(clip_id: int, account: SocialAccount, payload: Payload) -> None:
        post_checks.check_target(engine, clip_id, account.platform, payload, account.id)

    return check


def _post(engine: Engine, post_id: int) -> Post:
    """Return the post; 404 if there is none."""
    try:
        return posts.get_post(engine, post_id)
    except posts.PostNotFound as exc:
        raise not_found("post", post_id) from exc


def _clip(engine: Engine, clip_id: int) -> Clip:
    """Return the clip; 404 if there is none."""
    with Session(engine) as session:
        return clip_row(session, clip_id).to_model()


def _account(engine: Engine, account_id: int) -> SocialAccount:
    """Return the account; 404 if there is none."""
    try:
        return social_accounts.get_account(engine, account_id)
    except social_accounts.AccountNotFound as exc:
        raise not_found("account", account_id) from exc


def _payload(
    engine: Engine,
    account: SocialAccount | None,
    text: PostText,
    clip: Clip,
    platform: SocialPlatform | None = None,
) -> Payload:
    """Return the payload of text on the account's platform (platform if
    the account is gone), with the required hashtags where text has none of
    its own; 422 if the platform would refuse it."""
    target = platform if account is None else account.platform
    assert target is not None
    required = required_hashtags(engine, clip.project_id, account)
    try:
        return post_payload.build_payload(target, text, clip, required)
    except post_payload.PayloadInvalid as exc:
        raise ApiError(422, "validation_error", exc.message) from exc


def _locked(change: Callable[[], Post]) -> Post:
    """Run change; 409 post_locked if the post is past draft and queued."""
    try:
        return change()
    except posts.PostLocked as exc:
        raise ApiError(409, "post_locked", str(exc)) from exc


def _moved(change: Callable[[], Post]) -> Post:
    """Run change; 409 invalid_status if the post cannot move so."""
    try:
        return change()
    except posts.IllegalTransition as exc:
        raise ApiError(409, "invalid_status", str(exc)) from exc
