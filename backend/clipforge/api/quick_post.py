"""One-click quick post (owner request 2026-11-02): post a clip to the
owner's default accounts in one call.

    POST /clips/{id}/quick-post   QuickPost -> [Post] (201; human only)

The clip is rendered first if it is not (409 conflict while another render
is running). Each platform of the request posts to the account the body
names for it, else to the platform's default account (409
no_default_account); the platform's text is the body's, else the AI's
(post_copy.write_copy, with the always-included hashtags of the account).
Every post passes the publish checks (rights,
campaign, platform choices) before anything is saved; the uploads then run
right after the answer, as publish now does. The click is the human act
that publishing needs: API keys and the MCP server get 403 human_only.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import post_payload, posts, social_accounts, usage
from clipforge.api import post_checks
from clipforge.api.deps import (
    clip_row,
    get_engine,
    get_llm,
    project_row,
    require_human,
    work_dir,
)
from clipforge.api.errors import ApiError, not_found
from clipforge.clips import render_clip_row
from clipforge.llm import LLMClient
from clipforge.llm_http import LLMError
from clipforge.models import (
    Clip,
    Post,
    PostCopyRequest,
    PostText,
    SocialAccount,
    SocialPlatform,
)
from clipforge.pipeline.step import StepError
from clipforge.post_copy import PostCopyError, write_copy
from clipforge.post_tags import required_hashtags
from clipforge.posts import PublishBlocked
from clipforge.publishers.publish import rendered_video

logger = logging.getLogger(__name__)

router = APIRouter()


class QuickPost(BaseModel):
    """The body of POST /clips/{id}/quick-post: the platforms to post to
    (each one's default account), the accounts that replace a platform's
    default (their platform is posted to even if left out of platforms) and
    what the post says on each platform (left out: written by the AI)."""

    model_config = ConfigDict(extra="forbid")

    platforms: list[SocialPlatform] = Field(default_factory=list, max_length=4)
    account_ids: list[int] = Field(default_factory=list, max_length=50)
    texts: dict[SocialPlatform, PostText] = Field(default_factory=dict)


@router.post(
    "/clips/{clip_id}/quick-post",
    status_code=201,
    dependencies=[Depends(require_human)],
)
def quick_post(
    clip_id: int,
    body: QuickPost,
    background: BackgroundTasks,
    engine: Annotated[Engine, Depends(get_engine)],
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> list[Post]:
    """Render the clip if needed, then queue a post of it to each target
    account and upload them right after this answer. Refused as a whole
    (nothing queued) if a post fails the publish checks: 404 unknown clip
    or account, 409 no_default_account, 422 for text the platform would
    refuse, 502 llm_error if the AI cannot write a missing text."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
    accounts = _targets(engine, body)
    for account in accounts:
        post_checks.check_platform_name(account.platform)
    posts.require_rights(engine, clip_id)
    written: dict[tuple[SocialPlatform, tuple[str, ...]], PostText] = {}
    payloads = []
    for account in accounts:
        required = required_hashtags(engine, clip.project_id, account)
        key = (account.platform, tuple(required))
        if key not in written:
            written[key] = _text(engine, llm, clip, account.platform, body, required)
        payloads.append(_payload(account, written[key], clip, required))
    _render_if_needed(engine, clip)
    for account, payload in zip(accounts, payloads, strict=True):
        post_checks.check_target(engine, clip_id, account.platform, payload, account.id)
    created = [
        posts.queue_post(
            engine,
            posts.create_post(
                engine, clip_id=clip_id, account_id=a.id, payload=payload
            ).id,
            None,
        )
        for a, payload in zip(accounts, payloads, strict=True)
    ]
    for post in created:
        background.add_task(post_checks.run_publish, engine, post.id)
    return created


def _targets(engine: Engine, body: QuickPost) -> list[SocialAccount]:
    """Return the accounts to post to: the named ones, then the default of
    each other platform of the body; 409 no_default_account if one has
    none, 422 if there is nothing to post to."""
    chosen: dict[int, SocialAccount] = {}
    for account_id in body.account_ids:
        try:
            chosen[account_id] = social_accounts.get_account(engine, account_id)
        except social_accounts.AccountNotFound as exc:
            raise not_found("account", account_id) from exc
    covered = {account.platform for account in chosen.values()}
    for platform in dict.fromkeys(body.platforms):
        if platform in covered:
            continue
        default = social_accounts.default_account(engine, platform)
        if default is None:
            raise ApiError(
                409,
                "no_default_account",
                f"Connect a {platform} account and make it the default in "
                "Social accounts first.",
            )
        chosen[default.id] = default
    if not chosen:
        raise ApiError(422, "validation_error", "Choose a platform to post to.")
    return list(chosen.values())


def _text(
    engine: Engine,
    llm: LLMClient,
    clip: Clip,
    platform: SocialPlatform,
    body: QuickPost,
    required: list[str],
) -> PostText:
    """Return what the post says on platform: the body's text, else the AI's
    with the required hashtags (502 llm_error if it cannot write one, 409 if
    the clip has no transcript)."""
    given = body.texts.get(platform)
    if given is not None:
        return given
    with Session(engine) as session:
        credit = project_row(session, clip.project_id).credit_line
        work = work_dir(session, clip.project_id)
    request = PostCopyRequest(platform=platform)  # type: ignore[arg-type]
    try:
        with usage.recording(engine, clip.project_id):
            copy = write_copy(llm, request, clip, work, credit, required)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    except (LLMError, PostCopyError) as exc:
        logger.warning("clip %d: no post copy: %s", clip.id, exc)
        raise ApiError(502, "llm_error", str(exc)) from exc
    return PostText(title=copy.title, caption=copy.caption, hashtags=copy.hashtags)


def _payload(
    account: SocialAccount, text: PostText, clip: Clip, required: list[str]
) -> dict[str, Any]:
    """Return the platform's payload of text; 422 if it would refuse it."""
    try:
        return post_payload.build_payload(account.platform, text, clip, required)
    except post_payload.PayloadInvalid as exc:
        raise ApiError(422, "validation_error", exc.message) from exc


def _render_if_needed(engine: Engine, clip: Clip) -> None:
    """Render the clip if it has no video (409 conflict while it renders,
    500 render_failed if the render fails)."""
    try:
        rendered_video(clip)
        return
    except PublishBlocked:
        pass
    if clip.status == "rendering":
        raise ApiError(409, "conflict", f"clip {clip.id} is rendering; try later")
    with Session(engine) as session:
        work = work_dir(session, clip_row(session, clip.id).project_id)
    try:
        rendered = render_clip_row(engine, clip.id, work)
    except (StepError, ValueError) as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    if rendered.status != "rendered":
        raise ApiError(500, "render_failed", f"clip {clip.id} failed to render")
