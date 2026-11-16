"""Campaign preset and rule check endpoints (SPEC-v2 3.18).

    PUT /projects/{id}/campaign         ProjectCampaign -> Project
    GET /clips/{id}/campaign-check      ?platform= -> CampaignCheck

PUT applies the campaign's preset to the project and its clips
(campaign_presets). The publish and schedule endpoints depend on
require_campaign_rules, which answers 409 campaign_rules_failed with the
failed rules while a clip breaks one.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from clipforge import campaign_presets, campaign_rules
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError, not_found
from clipforge.campaigns import CampaignNotFound
from clipforge.models import CampaignCheck, Project, ProjectCampaign, SocialPlatform

router = APIRouter()


def require_campaign_rules(
    clip_id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    platform: SocialPlatform | None = None,
) -> CampaignCheck:
    """Dependency of the endpoints that publish or schedule a clip (path
    param clip_id, query or path param platform): 409 campaign_rules_failed
    with the failed rules ("failed": [RuleResult]) while the clip breaks a
    rule of its project's campaign (or, without one, has no source rights);
    404 if there is no such clip. Returns the passing check."""
    check = _check(engine, clip_id, platform)
    if not check.passed:
        failed = [r.model_dump() for r in check.results if not r.passed]
        raise ApiError(
            409,
            "campaign_rules_failed",
            campaign_rules.failed_message(check),
            {"failed": failed},
        )
    return check


@router.put("/projects/{project_id}/campaign")
def put_project_campaign(
    project_id: int,
    body: ProjectCampaign,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Project:
    """Make the campaign the project's and apply its preset (length range,
    caption template, credit line, hashtags, tags/mentions) to the project
    and its clips; null leaves the campaign. 404 for an unknown project, 422
    for an unknown campaign or one whose caption template is gone."""
    try:
        return campaign_presets.apply_campaign(engine, project_id, body.campaign_id)
    except campaign_presets.ProjectNotFound as exc:
        raise not_found("project", project_id) from exc
    except CampaignNotFound as exc:
        raise ApiError(422, "validation_error", f"campaign_id: {exc}") from exc
    except campaign_presets.UnknownCaptionTemplate as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc


@router.get("/clips/{clip_id}/campaign-check")
def get_campaign_check(
    clip_id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    platform: SocialPlatform | None = None,
) -> CampaignCheck:
    """Return the pass/fail of each campaign rule for the clip, published on
    platform (none: on any platform the campaign allows)."""
    return _check(engine, clip_id, platform)


def _check(
    engine: Engine, clip_id: int, platform: SocialPlatform | None
) -> CampaignCheck:
    """Check the clip on the local date; the 404 ApiError if it is missing."""
    try:
        return campaign_rules.check_saved_clip(engine, clip_id, date.today(), platform)
    except campaign_rules.ClipNotFound as exc:
        raise not_found("clip", clip_id) from exc
