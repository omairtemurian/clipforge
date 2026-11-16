"""Pro Edit audio library endpoints (SPEC-v3 5.1, 5.6), under /proedit.

Freesound sounds (CC0 and CC BY only) are searched and stored in the asset
library with their license, credit and source URL; the credits of the CC BY
sounds that a clip uses are appended to its description. The flag
proedit.enabled turns them off like the other Pro Edit endpoints.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import config
from clipforge.api.deps import clip_row, get_engine
from clipforge.api.errors import ApiError
from clipforge.api.proedit import require_proedit
from clipforge.assets import get_asset
from clipforge.models import Asset, Clip
from clipforge.proedit.audio import freesound
from clipforge.proedit.audio.credits import credit_clip
from clipforge.stock.base import ProviderDisabled, StockError

router = APIRouter(prefix="/proedit", dependencies=[Depends(require_proedit)])


class FreesoundDownload(BaseModel):
    """Which Freesound sound to store, as which kind of asset (SFX by
    default) and in which category (whoosh, riser, ...), if any."""

    sound_id: int = Field(ge=1)
    kind: Literal["sfx", "music", "audio"] = "sfx"
    category: str | None = Field(default=None, min_length=1, max_length=40)


class ClipCreditsBody(BaseModel):
    """The library assets whose sounds a clip uses."""

    asset_ids: list[int] = Field(min_length=1, max_length=200)


class ClipCredits(BaseModel):
    """The credit lines of the CC BY sounds of a clip and the clip with
    them appended to its description."""

    credits: list[str]
    clip: Clip


def _client() -> freesound.FreesoundClient:
    """Return the Freesound client of the configured key; 409
    provider_disabled ("Add a Freesound key ...") if there is none."""
    try:
        return freesound.FreesoundClient(config.settings.freesound_api_key)
    except ProviderDisabled as exc:
        raise ApiError(409, "provider_disabled", str(exc)) from exc


@router.get("/audio/freesound")
def get_freesound_status() -> freesound.FreesoundStatus:
    """Return whether the Freesound library is on (a key is set) and, if
    not, how to turn it on."""
    return freesound.status()


@router.get("/audio/freesound/search")
def search_freesound(
    tags: Annotated[str, Query(max_length=200)] = "",
    q: Annotated[str, Query(max_length=200)] = "",
    min_duration: Annotated[float, Query(ge=0, le=600)] = 0,
    max_duration: Annotated[float | None, Query(gt=0, le=600)] = None,
    limit: Annotated[int, Query(ge=1, le=150)] = 15,
) -> list[freesound.FreesoundSound]:
    """Return the CC0 and CC BY Freesound sounds that have all the
    comma-separated tags and match q, best match first. 422 without a tag
    and a query or with an invalid tag; 409 provider_disabled without a
    key; 502 stock_error if Freesound cannot be reached or refuses."""
    client = _client()
    names = [tag.strip() for tag in tags.split(",") if tag.strip()]
    try:
        return client.search(
            tags=names,
            query=q,
            min_duration_s=min_duration,
            max_duration_s=max_duration,
            page_size=limit,
        )
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    except StockError as exc:
        raise ApiError(502, "stock_error", str(exc)) from exc


@router.post("/audio/freesound/download")
def download_freesound(
    body: FreesoundDownload, engine: Annotated[Engine, Depends(get_engine)]
) -> Asset:
    """Store sound body.sound_id (its license checked again on Freesound's
    answer) in the asset library and return the asset. 422 license_rejected
    if it is not CC0 or CC BY; 409 provider_disabled without a key; 502
    stock_error if Freesound or its download fails."""
    client = _client()
    try:
        sound = client.sound(body.sound_id)
        with Session(engine) as session:
            return freesound.download_sound(
                session, sound, kind=body.kind, category=body.category
            )
    except freesound.LicenseRejected as exc:
        raise ApiError(422, "license_rejected", str(exc)) from exc
    except StockError as exc:
        raise ApiError(502, "stock_error", str(exc)) from exc


@router.post("/clips/{clip_id}/credits")
def add_clip_credits(
    clip_id: int,
    body: ClipCreditsBody,
    engine: Annotated[Engine, Depends(get_engine)],
) -> ClipCredits:
    """Append the credits of the CC BY assets among body.asset_ids to the
    description of clip clip_id (each once) and return the credit lines and
    the clip. 404 if the clip or an asset does not exist."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        assets = []
        for asset_id in body.asset_ids:
            asset = get_asset(session, asset_id)
            if asset is None:
                raise ApiError(404, "not_found", f"asset {asset_id} not found")
            assets.append(asset)
        lines = credit_clip(session, row, assets)
        return ClipCredits(credits=lines, clip=row.to_model())
