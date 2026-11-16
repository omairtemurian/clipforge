"""The Approval Inbox endpoints of the autopilot (SPEC-v2 3.19).

    GET  /drafts                         ?status=&campaign_id= -> [Draft]
    GET  /drafts/{id}                    -> Draft
    POST /drafts                         DraftCreate -> Draft (201)
    POST /drafts/{id}/notes              DraftNoteCreate -> Draft (201)
    POST /drafts/{id}/approve            DraftApprove -> DraftApproval (owner)
    POST /drafts/{id}/reject             DraftReject -> Draft (owner)
    POST /campaigns/{id}/drafts/approve  DraftApprove -> [DraftApproval] (owner)

Approval is human-only: approving (which queues the clip's posts into the
next free slots) and rejecting need the owner's app session, and an API key
or the MCP server gets 403 human_only (api.deps.require_human). Agents may
list the inbox, make drafts of campaign clips and add review notes. The
posts of an approved draft pass the publish checks first (api.posts), so a
needs_fix draft is approved only once its clip passes the campaign's rules.
"""

from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import Engine

from clipforge import campaign_accounts, campaigns, social_accounts
from clipforge.api.deps import get_engine, is_agent_call, require_human
from clipforge.api.errors import ApiError, not_found
from clipforge.api.posts import bulk_schedule as schedule_posts
from clipforge.autopilot import inbox
from clipforge.models import (
    Draft,
    DraftApproval,
    DraftApprove,
    DraftCreate,
    DraftNoteAuthor,
    DraftNoteCreate,
    DraftReject,
    DraftStatus,
    Post,
)

router = APIRouter()

EngineDep = Annotated[Engine, Depends(get_engine)]
HUMAN_ONLY = [Depends(require_human)]


@router.get("/drafts")
def list_drafts(
    engine: EngineDep,
    status: DraftStatus | None = None,
    campaign_id: int | None = None,
) -> list[Draft]:
    """List the drafts, newest first (status and campaign_id filter them);
    the old ones expire first."""
    return inbox.list_drafts(engine, status, campaign_id)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int, engine: EngineDep) -> Draft:
    """Return one draft."""
    try:
        return inbox.get_draft(engine, draft_id)
    except inbox.DraftNotFound as exc:
        raise not_found("draft", draft_id) from exc


@router.post("/drafts", status_code=201)
def create_draft(body: DraftCreate, engine: EngineDep) -> Draft:
    """Make a draft of a clip of a campaign's project for the owner to
    decide on: pending if it passes the campaign's rules, else needs_fix.
    404 for an unknown clip, 422 for a clip in no campaign, 409
    draft_exists if the clip has one."""
    try:
        return inbox.create_draft(engine, body.clip_id)
    except inbox.ClipNotFound as exc:
        raise not_found("clip", body.clip_id) from exc
    except inbox.NotInCampaign as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    except inbox.DraftExists as exc:
        raise ApiError(409, "draft_exists", str(exc)) from exc


@router.post("/drafts/{draft_id}/notes", status_code=201)
def add_draft_note(
    draft_id: int, body: DraftNoteCreate, request: Request, engine: EngineDep
) -> Draft:
    """Add a review note to a draft (by the owner, or by an agent when the
    call has an API key); 409 too_many_notes past the limit."""
    by: DraftNoteAuthor = "agent" if is_agent_call(request) else "owner"
    try:
        return inbox.add_note(engine, draft_id, body.text, by)
    except inbox.DraftNotFound as exc:
        raise not_found("draft", draft_id) from exc
    except inbox.TooManyNotes as exc:
        raise ApiError(409, "too_many_notes", str(exc)) from exc


@router.post("/drafts/{draft_id}/approve", dependencies=HUMAN_ONLY)
def approve_draft(
    draft_id: int, body: DraftApprove, request: Request, engine: EngineDep
) -> DraftApproval:
    """Approve a waiting draft (the owner only): queue its clip's posts in
    the next free slots of the rules and mark it approved. 409
    draft_decided if it no longer waits; the posting errors of
    POST /posts/bulk-schedule otherwise."""
    draft = _waiting(engine, draft_id)
    (approval,) = _approve(engine, request, draft.campaign_id, [draft], body)
    return approval


@router.post("/drafts/{draft_id}/reject", dependencies=HUMAN_ONLY)
def reject_draft(draft_id: int, body: DraftReject, engine: EngineDep) -> Draft:
    """Reject a waiting draft (the owner only), with the reason if given;
    409 draft_decided if it no longer waits."""
    try:
        return inbox.reject(engine, draft_id, body.reason)
    except inbox.DraftNotFound as exc:
        raise not_found("draft", draft_id) from exc
    except inbox.DraftDecided as exc:
        raise ApiError(409, "draft_decided", str(exc)) from exc


@router.post("/campaigns/{campaign_id}/drafts/approve", dependencies=HUMAN_ONLY)
def approve_campaign_drafts(
    campaign_id: int, body: DraftApprove, request: Request, engine: EngineDep
) -> list[DraftApproval]:
    """Approve every pending draft of the campaign (the owner only, after the
    app's confirm dialog), oldest first; none if no draft is pending."""
    try:
        campaigns.get_campaign(engine, campaign_id)
    except campaigns.CampaignNotFound as exc:
        raise not_found("campaign", campaign_id) from exc
    drafts = inbox.pending_drafts(engine, campaign_id)
    if not drafts:
        return []
    return _approve(engine, request, campaign_id, drafts, body)


def _waiting(engine: Engine, draft_id: int) -> Draft:
    """Return the draft if it waits; 404, 409 draft_decided otherwise."""
    try:
        return inbox.waiting_draft(engine, draft_id)
    except inbox.DraftNotFound as exc:
        raise not_found("draft", draft_id) from exc
    except inbox.DraftDecided as exc:
        raise ApiError(409, "draft_decided", str(exc)) from exc


def _approve(
    engine: Engine,
    request: Request,
    campaign_id: int,
    drafts: list[Draft],
    body: DraftApprove,
) -> list[DraftApproval]:
    """Queue the posts of the drafts' clips (api.posts.bulk_schedule with
    queue, so each passes the publish checks), then mark them approved."""
    try:
        plan = inbox.approval_plan(
            engine, campaign_id, [d.clip_id for d in drafts], body
        )
    except social_accounts.AccountNotFound as exc:
        raise ApiError(404, "not_found", str(exc)) from exc
    except (
        inbox.NoSlots,
        campaign_accounts.NoCampaignAccounts,
        campaign_accounts.PlatformNotAllowed,
    ) as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    queued = schedule_posts(plan, request, engine)
    by_clip: defaultdict[int, list[Post]] = defaultdict(list)
    for post in queued:
        by_clip[post.clip_id].append(post)
    approved = inbox.mark_approved(engine, [d.id for d in drafts])
    return [DraftApproval(draft=d, posts=by_clip[d.clip_id]) for d in approved]
