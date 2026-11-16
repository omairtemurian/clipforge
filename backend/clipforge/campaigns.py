"""Clipping campaigns (SPEC-v2 3.18): the owner's own records of a campaign and
of the evidence that they may clip its creator.

Everything is entered by the owner; nothing here fetches a campaign board or
a creator's site. The permission evidence is the page that grants it
(permission_source_url), a screenshot kept as an asset in
{data_dir}/campaigns/<id>/ and the date it was saved; publishing for a
project of the campaign is blocked until all three are there
(require_permission), as the copyright guard of SPEC-v2 1.6 does for a
project's source rights.
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import Engine, update
from sqlmodel import Session, col, select

from clipforge import assets, auto_import, config
from clipforge.campaign_rows import CampaignRow
from clipforge.db import ProjectRow
from clipforge.models import Campaign, CampaignCreate, CampaignPatch

CAMPAIGNS_DIRNAME = "campaigns"
SCREENSHOT_TAG = "campaign-permission"
SCREENSHOT_LICENSE = "user-provided"
# What the owner must still add, by missing piece (in the order shown).
MISSING_URL = "the permission source URL"
MISSING_SCREENSHOT = "a screenshot of the permission"
MISSING_DATE = "the date the permission was checked"


class CampaignNotFound(LookupError):
    """No campaign has the id."""


class PermissionMissing(Exception):
    """A project's campaign lacks permission evidence; missing lists what."""

    def __init__(self, campaign: Campaign, missing: list[str]) -> None:
        super().__init__(
            f"campaign {campaign.name!r} needs {', '.join(missing)} before "
            "anything of it is published"
        )
        self.campaign_id = campaign.id
        self.missing = missing


def campaign_dir(campaign_id: int) -> Path:
    """Return the directory of a campaign's files."""
    return config.settings.data_dir / CAMPAIGNS_DIRNAME / str(campaign_id)


def create_campaign(engine: Engine, create: CampaignCreate) -> Campaign:
    """Add a campaign. permission_checked_at is set now if a permission source
    URL is given; the screenshot is added with set_permission_screenshot."""
    row = CampaignRow(**create.model_dump())
    if row.permission_source_url:
        row.permission_checked_at = _now()
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def list_campaigns(engine: Engine) -> list[Campaign]:
    """Return the campaigns, oldest first."""
    with Session(engine) as session:
        rows = session.exec(select(CampaignRow).order_by(col(CampaignRow.id)))
        return [row.to_model() for row in rows]


def get_campaign(engine: Engine, campaign_id: int) -> Campaign:
    """Return a campaign; raise CampaignNotFound if there is none."""
    with Session(engine) as session:
        return _row(session, campaign_id).to_model()


def update_campaign(engine: Engine, campaign_id: int, patch: CampaignPatch) -> Campaign:
    """Change the fields of a campaign that patch sends and return it.

    Raise CampaignNotFound if there is none and pydantic's ValidationError if
    the result is invalid (min_duration_s over max_duration_s); nothing
    changes then. Saving a new permission source URL sets
    permission_checked_at to now; clearing it clears the date.
    """
    with Session(engine) as session:
        row = _row(session, campaign_id)
        changes = patch.model_dump(mode="json", include=patch.model_fields_set)
        merged = CampaignCreate.model_validate(
            row.to_model().model_dump(mode="json") | changes
        )
        for name in changes:
            setattr(row, name, getattr(merged, name))
        if "permission_source_url" in changes:
            row.permission_checked_at = _now() if row.permission_source_url else None
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def delete_campaign(engine: Engine, campaign_id: int) -> None:
    """Delete a campaign with its permission screenshot (asset and file);
    the projects that belonged to it stay, without a campaign; the channels
    it registered in Auto Import are removed. Raise CampaignNotFound if there
    is none."""
    with Session(engine) as session:
        row = _row(session, campaign_id)
        screenshot = row.permission_screenshot_asset_id
        session.execute(
            update(ProjectRow)
            .where(col(ProjectRow.campaign_id) == campaign_id)
            .values(campaign_id=None)
        )
        session.delete(row)
        session.commit()
        auto_import.remove_campaign_channels(engine, campaign_id)
        if screenshot is not None:
            _drop_asset(session, screenshot)
    shutil.rmtree(campaign_dir(campaign_id), ignore_errors=True)


def set_permission_screenshot(
    engine: Engine, campaign_id: int, data: bytes, suffix: str
) -> Campaign:
    """Keep data, an image the caller has checked, as the permission
    screenshot of a campaign (suffix: .png, .jpg or .webp) and return the
    campaign with its date set to now.

    The image is stored as {data_dir}/campaigns/<id>/permission<suffix> and
    registered as an asset (replacing the screenshot of before). Raise
    CampaignNotFound if there is none.
    """
    with Session(engine) as session:
        row = _row(session, campaign_id)
        directory = campaign_dir(campaign_id)
        directory.mkdir(parents=True, exist_ok=True)
        previous = row.permission_screenshot_asset_id
        for old in directory.glob("permission.*"):
            old.unlink()
        path = directory / f"permission{suffix}"
        path.write_bytes(data)
        asset = assets.add_asset(
            session,
            "image",
            str(path),
            SCREENSHOT_LICENSE,
            source_url=row.permission_source_url,
            tags=[SCREENSHOT_TAG],
        )
        row.permission_screenshot_asset_id = asset.id
        row.permission_checked_at = _now()
        session.add(row)
        session.commit()
        if previous is not None:
            _drop_asset(session, previous)
        session.refresh(row)
        return row.to_model()


def screenshot_path(engine: Engine, campaign_id: int) -> Path | None:
    """Return the file of a campaign's permission screenshot, None if it has
    none. Raise CampaignNotFound if there is no such campaign."""
    with Session(engine) as session:
        asset_id = _row(session, campaign_id).permission_screenshot_asset_id
        asset = None if asset_id is None else assets.get_asset(session, asset_id)
    return None if asset is None else Path(asset.path)


def permission_missing(campaign: Campaign) -> list[str]:
    """Return what the campaign's permission evidence still lacks (the URL, the
    screenshot, the date), empty once it is complete."""
    missing = []
    if not campaign.permission_source_url:
        missing.append(MISSING_URL)
    if campaign.permission_screenshot_asset_id is None:
        missing.append(MISSING_SCREENSHOT)
    if campaign.permission_checked_at is None:
        missing.append(MISSING_DATE)
    return missing


def require_permission(engine: Engine, project_id: int) -> None:
    """Check that project project_id may be published as far as its campaign
    goes: a project without a campaign passes; a project of a campaign needs
    the campaign's permission evidence (PermissionMissing says what is
    lacking). Publishing and scheduling call this before they act."""
    with Session(engine) as session:
        project = session.get(ProjectRow, project_id)
        campaign_id = None if project is None else project.campaign_id
        if campaign_id is None:
            return
        campaign = _row(session, campaign_id).to_model()
    missing = permission_missing(campaign)
    if missing:
        raise PermissionMissing(campaign, missing)


def validation_message(error: ValidationError) -> str:
    """Return the first problem of a ValidationError as a sentence."""
    first = error.errors()[0]
    where = ".".join(str(part) for part in first["loc"])
    return f"{where}: {first['msg']}" if where else str(first["msg"])


def _row(session: Session, campaign_id: int) -> CampaignRow:
    """Return a campaign's row; raise CampaignNotFound if there is none."""
    row = session.get(CampaignRow, campaign_id)
    if row is None:
        raise CampaignNotFound(f"campaign {campaign_id} not found")
    return row


def _drop_asset(session: Session, asset_id: int) -> None:
    """Delete asset asset_id from the library if it is still there."""
    try:
        assets.delete_asset(session, asset_id)
    except assets.AssetNotFoundError:
        pass


def _now() -> datetime:
    return datetime.now(UTC)
