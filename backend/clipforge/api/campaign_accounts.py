"""The accounts of a clipping campaign and its bulk scheduler (SPEC-v2
3.18: map each campaign to the clipper's own accounts; bulk schedule per
campaign).

    GET  /campaigns/{id}/accounts        -> [SocialAccount]
    PUT  /campaigns/{id}/accounts        CampaignAccounts -> [SocialAccount]
    POST /campaigns/{id}/bulk-schedule   CampaignBulkSchedule -> [Post] (201)

The bulk scheduler posts every clip to each of the campaign's accounts, as
POST /posts/bulk-schedule does (drafts, or queued by the owner only).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import Engine

from clipforge import campaign_accounts, campaigns, social_accounts
from clipforge.api.deps import get_engine, require_human
from clipforge.api.errors import ApiError, not_found
from clipforge.api.posts import bulk_schedule as schedule_posts
from clipforge.models import (
    BulkSchedule,
    Campaign,
    CampaignAccounts,
    CampaignBulkSchedule,
    Post,
    SocialAccount,
)

router = APIRouter(prefix="/campaigns/{campaign_id}")

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("/accounts")
def get_campaign_accounts(campaign_id: int, engine: EngineDep) -> list[SocialAccount]:
    """Return the accounts that the campaign is run on."""
    try:
        return campaign_accounts.list_accounts(engine, campaign_id)
    except campaigns.CampaignNotFound as exc:
        raise not_found("campaign", campaign_id) from exc


@router.put("/accounts")
def put_campaign_accounts(
    campaign_id: int, body: CampaignAccounts, engine: EngineDep
) -> list[SocialAccount]:
    """Run the campaign on these of the owner's accounts, replacing the ones
    before; 404 for an unknown account, 422 for an account on a platform the
    campaign does not allow."""
    try:
        return campaign_accounts.set_accounts(engine, campaign_id, body.account_ids)
    except campaigns.CampaignNotFound as exc:
        raise not_found("campaign", campaign_id) from exc
    except social_accounts.AccountNotFound as exc:
        raise ApiError(404, "not_found", str(exc)) from exc
    except campaign_accounts.PlatformNotAllowed as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc


@router.post("/bulk-schedule", status_code=201)
def campaign_bulk_schedule(
    campaign_id: int,
    body: CampaignBulkSchedule,
    request: Request,
    engine: EngineDep,
) -> list[Post]:
    """Post every clip to each account of the campaign, each in the
    account's next free slot of the rules, as drafts or queued with
    body.queue (human only). 422 if the campaign has no accounts or a clip
    is not in a project of the campaign. Queueing is checked first: an
    agent gets 403 human_only before any other answer."""
    if body.queue:
        require_human(request)
    campaign = _campaign(engine, campaign_id)
    try:
        targets = campaign_accounts.bulk_targets(engine, campaign, body.text)
        campaign_accounts.check_clips(engine, campaign, body.clip_ids)
    except (
        campaign_accounts.NoCampaignAccounts,
        campaign_accounts.PlatformNotAllowed,
        campaign_accounts.ClipsNotInCampaign,
    ) as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    bulk = BulkSchedule(
        clip_ids=body.clip_ids, targets=targets, rules=body.rules, queue=body.queue
    )
    return schedule_posts(bulk, request, engine)


def _campaign(engine: Engine, campaign_id: int) -> Campaign:
    """Return the campaign; 404 if there is none."""
    try:
        return campaigns.get_campaign(engine, campaign_id)
    except campaigns.CampaignNotFound as exc:
        raise not_found("campaign", campaign_id) from exc
