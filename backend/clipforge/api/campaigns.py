"""Clipping campaign endpoints (SPEC-v2 3.18): the owner's campaigns and the
evidence that they may clip the creator (the permission source URL, a
screenshot and the date).

    GET    /campaigns                           -> [Campaign]
    POST   /campaigns                           CampaignCreate -> Campaign
    GET    /campaigns/{id}                      -> Campaign
    PATCH  /campaigns/{id}                      CampaignPatch  -> Campaign
    DELETE /campaigns/{id}                      -> 204
    POST   /campaigns/{id}/permission-screenshot  file -> Campaign
    GET    /campaigns/{id}/permission-screenshot  -> the image

The publish and schedule endpoints depend on require_campaign_permission.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import Engine

from clipforge import campaign_presets, campaign_watch, campaigns
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError, not_found
from clipforge.brand_files import MAX_LOGO_BYTES, image_suffix
from clipforge.models import Campaign, CampaignCreate, CampaignPatch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns")

T = TypeVar("T")
MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}


def require_campaign_permission(
    project_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> None:
    """Dependency of the endpoints that publish or schedule a project's
    clips: 409 permission_missing while the project's campaign lacks the
    permission source URL, the screenshot or the date. A project without a
    campaign passes."""
    try:
        campaigns.require_permission(engine, project_id)
    except campaigns.PermissionMissing as exc:
        raise ApiError(409, "permission_missing", str(exc)) from exc


@router.get("")
def list_campaigns(engine: Annotated[Engine, Depends(get_engine)]) -> list[Campaign]:
    """Return the campaigns, oldest first."""
    return campaigns.list_campaigns(engine)


@router.post("", status_code=201)
def create_campaign(
    body: CampaignCreate, engine: Annotated[Engine, Depends(get_engine)]
) -> Campaign:
    """Add a campaign; its permission date is set now if a permission source
    URL is given (the screenshot is uploaded afterwards). 422 if its caption
    template does not exist. The YouTube channels among its source channel
    URLs are registered in Auto Import (campaign_watch)."""
    _check_template(body.caption_template)
    return _watching(engine, campaigns.create_campaign(engine, body))


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Campaign:
    """Return one campaign."""
    return _found(lambda: campaigns.get_campaign(engine, campaign_id), campaign_id)


@router.patch("/{campaign_id}")
def patch_campaign(
    campaign_id: int,
    body: CampaignPatch,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Campaign:
    """Change the fields of a campaign that are sent (422 if the result is
    invalid, e.g. a minimum duration over the maximum). A new permission
    source URL sets the permission date to now. The campaign's YouTube
    channels are registered in Auto Import again (campaign_watch)."""
    if "caption_template" in body.model_fields_set:
        _check_template(body.caption_template)

    def change() -> Campaign:
        try:
            return campaigns.update_campaign(engine, campaign_id, body)
        except ValidationError as exc:
            raise ApiError(
                422, "validation_error", campaigns.validation_message(exc)
            ) from exc

    return _watching(engine, _found(change, campaign_id))


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(
    campaign_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Response:
    """Delete a campaign and its screenshot; its projects stay, without a
    campaign."""
    _found(lambda: campaigns.delete_campaign(engine, campaign_id), campaign_id)
    return Response(status_code=204)


@router.post("/{campaign_id}/permission-screenshot")
def upload_permission_screenshot(
    campaign_id: int,
    file: UploadFile,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Campaign:
    """Keep an uploaded PNG, JPEG or WebP image (up to 5 MB) as the
    campaign's permission screenshot, replacing the one before, and set the
    permission date to now; 422 if the file is not such an image."""
    _found(lambda: campaigns.get_campaign(engine, campaign_id), campaign_id)
    data = file.file.read(MAX_LOGO_BYTES + 1)
    if not data:
        raise ApiError(422, "validation_error", "file: the file is empty")
    if len(data) > MAX_LOGO_BYTES:
        raise ApiError(422, "validation_error", "file: the file is over 5 MB")
    suffix = image_suffix(data[:12])
    if suffix is None:
        raise ApiError(422, "validation_error", "file: must be a PNG, JPEG or WebP")
    saved = _found(
        lambda: campaigns.set_permission_screenshot(engine, campaign_id, data, suffix),
        campaign_id,
    )
    return _watching(engine, saved)


@router.get("/{campaign_id}/permission-screenshot")
def get_permission_screenshot(
    campaign_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve the campaign's permission screenshot; 404 if it has none."""
    path = _found(lambda: campaigns.screenshot_path(engine, campaign_id), campaign_id)
    if path is None or not path.is_file():
        raise ApiError(
            404, "not_found", f"campaign {campaign_id} has no permission screenshot"
        )
    return FileResponse(path, media_type=MEDIA_TYPES[path.suffix])


def _watching(engine: Engine, campaign: Campaign) -> Campaign:
    """Register the campaign's YouTube channels in Auto Import and return the
    campaign; the links that cannot be watched are logged."""
    today = datetime.now(UTC).date()
    for url, reason in campaign_watch.sync_channels(engine, campaign, today).skipped:
        logger.info("campaign %d: not watching %s: %s", campaign.id, url, reason)
    return campaign


def _check_template(name: str | None) -> None:
    """Answer 422 if name is not a caption template (None passes)."""
    try:
        campaign_presets.check_caption_template(name)
    except campaign_presets.UnknownCaptionTemplate as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc


def _found(action: Callable[[], T], campaign_id: int) -> T:
    """Run action; turn CampaignNotFound into the 404 ApiError."""
    try:
        return action()
    except campaigns.CampaignNotFound as exc:
        raise not_found("campaign", campaign_id) from exc
