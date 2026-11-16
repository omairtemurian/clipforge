"""The autopilot settings of a campaign (SPEC-v2 3.19).

    GET /campaigns/{id}/autopilot   -> AutopilotSettings
    PUT /campaigns/{id}/autopilot   AutopilotSettingsUpdate -> AutopilotSettings
    GET /autopilot/status           -> AutopilotStatus
    PUT /autopilot/pause            AutopilotPauseUpdate -> AutopilotStatus

The settings only say how drafts are made; the autopilot never publishes,
schedules or submits (the owner approves each draft). The status says
whether every autopilot is paused (the global "Pause all autopilot") and
which campaigns' autopilots are stopped by a safety switch. Anyone may
pause; only the owner may resume (403 human_only for an API key or agent).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import Engine

from clipforge import campaign_accounts, campaigns, social_accounts
from clipforge.api.deps import get_engine, require_human
from clipforge.api.errors import ApiError, not_found
from clipforge.autopilot import safety, settings
from clipforge.campaign_presets import UnknownCaptionTemplate
from clipforge.models import (
    AutopilotPauseUpdate,
    AutopilotSettings,
    AutopilotSettingsUpdate,
    AutopilotStatus,
)

router = APIRouter()

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("/campaigns/{campaign_id}/autopilot")
def get_autopilot(campaign_id: int, engine: EngineDep) -> AutopilotSettings:
    """Return the campaign's autopilot settings (the defaults, off, if it was
    never set up)."""
    try:
        return settings.get_settings(engine, campaign_id)
    except campaigns.CampaignNotFound as exc:
        raise not_found("campaign", campaign_id) from exc


@router.put("/campaigns/{campaign_id}/autopilot")
def put_autopilot(
    campaign_id: int, body: AutopilotSettingsUpdate, engine: EngineDep
) -> AutopilotSettings:
    """Save the campaign's autopilot settings, replacing the ones before; 404
    for an unknown account or brand template, 422 for an account on a
    platform the campaign does not allow, an unknown caption template, more
    than 5 posts a day or a day of slots over the daily limit."""
    try:
        return settings.save_settings(engine, campaign_id, body)
    except campaigns.CampaignNotFound as exc:
        raise not_found("campaign", campaign_id) from exc
    except (social_accounts.AccountNotFound, settings.BrandTemplateNotFound) as exc:
        raise ApiError(404, "not_found", str(exc)) from exc
    except (
        campaign_accounts.PlatformNotAllowed,
        UnknownCaptionTemplate,
    ) as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc


@router.get("/autopilot/status")
def get_autopilot_status(engine: EngineDep) -> AutopilotStatus:
    """Return whether every autopilot is paused and why the campaigns'
    autopilots that are on are stopped."""
    return safety.status(engine)


@router.put("/autopilot/pause")
def put_autopilot_pause(
    body: AutopilotPauseUpdate, request: Request, engine: EngineDep
) -> AutopilotStatus:
    """Pause or resume every campaign's autopilot; return the status.
    Resuming is the owner's: 403 human_only for an API key or agent."""
    if not body.paused:
        require_human(request)
    safety.set_paused(engine, body.paused)
    return safety.status(engine)
