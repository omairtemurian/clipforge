"""B-roll endpoints (SPEC-v2 3.6): find the spots of a clip that stock
footage helps, review what the stock providers have for them, and put,
replace or remove B-roll on the clip's broll track.

GET /broll/providers says which stock providers have an API key; GET
/broll/search searches one (to look for other footage than a spot's).
POST /clips/{id}/broll/spots asks the LLM for the sentences of the saved
clip that B-roll helps and their keywords (pipeline/broll), searches stock
video for each and returns the spots to review; it saves nothing, so
calling it again regenerates them. POST /clips/{id}/broll puts a stock
video (downloaded into the asset library with its license and
attribution) or a library video or image on the broll track as a
full-screen cutaway or a picture-in-picture; PUT /clips/{id}/broll/{item}
replaces what an item shows (same times and look) and DELETE removes it.
Each change answers the clip and stores a version (undo); the rendered
video is not changed: render the clip again.

Errors: 404 if the clip, item or asset does not exist; 409 while the clip
renders, if the transcript is missing or no stock provider has an API key
(provider_disabled); 422 for a body that is not valid or B-roll that does
not fit the clip; 502 if the LLM cannot be reached or sends no valid
spots (llm_error) or a stock search or download fails (stock_error).
"""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import assets, config, stock, usage
from clipforge.api.deps import (
    clip_row,
    get_engine,
    get_llm,
    project_row,
    require_usage_budget,
    work_dir,
)
from clipforge.api.errors import ApiError
from clipforge.api.timeline import store_tracks
from clipforge.clip_text import clip_caption_words
from clipforge.db import ClipRow
from clipforge.ffmpeg import FFmpegError, probe_media
from clipforge.llm import LLMClient
from clipforge.llm_http import LLMError
from clipforge.models import (
    BrollInsert,
    BrollProps,
    BrollSource,
    BrollSpot,
    BrollSpotsOptions,
    Clip,
    StockClip,
    StockProviderStatus,
    StockSource,
    TrackItem,
    TrackItemKind,
)
from clipforge.pipeline.broll import (
    BrollError,
    broll_item,
    clip_sentences,
    find_spots,
    next_item_id,
    plan_spots,
    stock_orientation,
)
from clipforge.pipeline.step import StepError
from clipforge.timeline import clip_length

logger = logging.getLogger(__name__)

router = APIRouter()
# Stock results per search, and the kinds of library asset B-roll shows.
RESULTS_PER_SPOT = 6
ITEM_KINDS: dict[str, TrackItemKind] = {
    "video": "video",
    "image": "image",
    "logo": "image",
}


@router.get("/broll/providers")
def list_providers() -> list[StockProviderStatus]:
    """Return whether each stock provider can be searched."""
    return stock.provider_statuses()


@router.get("/broll/search")
def search_stock(
    query: Annotated[str, Query(min_length=1, max_length=100)],
    provider: StockSource | None = None,
    orientation: Annotated[
        str | None, Query(pattern="^(landscape|portrait|square)$")
    ] = None,
    min_seconds: Annotated[float, Query(ge=0, le=60)] = 0,
) -> list[StockClip]:
    """Return the stock videos of provider (None: the first with an API
    key) for query, of orientation, at least min_seconds long."""
    client = _stock_provider(provider)
    try:
        return client.search(
            query,
            orientation=orientation,
            min_duration_s=min_seconds,
            per_page=RESULTS_PER_SPOT,
        )
    except stock.StockError as exc:
        raise ApiError(502, "stock_error", str(exc)) from exc


@router.post("/clips/{clip_id}/broll/spots")
def find_broll_spots(
    clip_id: int,
    body: BrollSpotsOptions,
    engine: Annotated[Engine, Depends(get_engine)],
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> list[BrollSpot]:
    """Return the B-roll spots of the saved clip (pipeline/broll), each with
    the stock videos found for it, in time order."""
    client = _stock_provider(body.provider)
    require_usage_budget(engine)
    fps = config.settings.render.fps
    with Session(engine) as session:
        clip = _editable(session, clip_id).to_model()
        work = work_dir(session, clip.project_id)
        aspect = (
            clip.framing.aspect or project_row(session, clip.project_id).settings.aspect
        )
    try:
        sentences = clip_sentences(clip_caption_words(work, clip))
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    orientation = stock_orientation(aspect, body.mode)
    with usage.recording(engine, clip.project_id):
        try:
            picks = find_spots(llm, sentences, body.max_spots, clip.id)
        except (LLMError, BrollError) as exc:
            logger.warning("clip %d: no B-roll spots from the LLM: %s", clip.id, exc)
            raise ApiError(502, "llm_error", str(exc)) from exc
        spots = plan_spots(picks, sentences, clip_length(clip, fps))
        return [_with_results(client, spot, orientation) for spot in spots]


@router.post("/clips/{clip_id}/broll")
def add_broll(
    clip_id: int, body: BrollInsert, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Put body's source on clip clip_id's broll track; return the clip."""
    props = BrollProps(mode=body.mode, x=body.x, y=body.y, width=body.width)
    with Session(engine) as session:
        row = _editable(session, clip_id)
        clip = row.to_model()
        asset_id, kind, seconds = _source(session, body)
        item = _item(next_item_id(clip.tracks), asset_id, kind, body, props, seconds)
        return _save(session, row, [*clip.tracks.broll, item])


@router.put("/clips/{clip_id}/broll/{item_id}")
def replace_broll(
    clip_id: int,
    item_id: str,
    body: BrollSource,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Clip:
    """Make B-roll item item_id of clip clip_id show body's source from the
    same start (to the same end at most) with the same props; return the
    clip."""
    with Session(engine) as session:
        row = _editable(session, clip_id)
        clip = row.to_model()
        old = _broll(clip, item_id)
        props = BrollProps.model_validate(old.props).model_copy(update={"offset": 0})
        asset_id, kind, seconds = _source(session, body)
        new = _item(item_id, asset_id, kind, old, props, seconds)
        items = [new if item.id == item_id else item for item in clip.tracks.broll]
        return _save(session, row, items)


@router.delete("/clips/{clip_id}/broll/{item_id}")
def remove_broll(
    clip_id: int, item_id: str, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Remove B-roll item item_id from clip clip_id; return the clip."""
    with Session(engine) as session:
        row = _editable(session, clip_id)
        clip = row.to_model()
        _broll(clip, item_id)
        items = [item for item in clip.tracks.broll if item.id != item_id]
        return _save(session, row, items)


def _stock_provider(name: StockSource | None) -> stock.StockProvider:
    """Return the client of stock provider name (None: the first with an
    API key); 409 provider_disabled if it has no key."""
    if name is None:
        enabled = [s.provider for s in stock.provider_statuses() if s.enabled]
        if not enabled:
            raise ApiError(
                409,
                "provider_disabled",
                "no stock provider has an API key: set PEXELS_API_KEY or "
                "PIXABAY_API_KEY in .env",
            )
        name = enabled[0]
    try:
        return stock.provider(name)
    except stock.ProviderDisabled as exc:
        raise ApiError(409, "provider_disabled", str(exc)) from exc


def _with_results(
    client: stock.StockProvider, spot: BrollSpot, orientation: str
) -> BrollSpot:
    """Return spot with the stock videos client finds for its query that
    last as long as it; a failed search is the spot's error."""
    try:
        found = client.search(
            spot.query,
            orientation=orientation,
            min_duration_s=spot.end - spot.start,
            per_page=RESULTS_PER_SPOT,
        )
    except stock.StockError as exc:
        logger.warning("B-roll search %r failed: %s", spot.query, exc)
        return spot.model_copy(update={"error": str(exc)})
    return spot.model_copy(update={"results": found})


def _editable(session: Session, clip_id: int) -> ClipRow:
    """Return clip clip_id's row: 404 if there is none, 409 while it renders."""
    row = clip_row(session, clip_id)
    if row.status == "rendering":
        raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
    return row


def _broll(clip: Clip, item_id: str) -> TrackItem:
    """Return the clip's B-roll item item_id (404 if it has none)."""
    found = next((item for item in clip.tracks.broll if item.id == item_id), None)
    if found is None:
        raise ApiError(404, "not_found", f"clip {clip.id} has no B-roll {item_id}")
    return found


def _source(
    session: Session, body: BrollSource
) -> tuple[int, TrackItemKind, float | None]:
    """Return the asset id, item kind and length in seconds (None for an
    image or a video ffprobe cannot read) of body's source: a stock video
    is downloaded into the asset library (502 if that fails); a library
    asset must be a video or an image (404 if there is none, 422 if it is
    something else)."""
    if body.stock is not None:
        try:
            asset = stock.download_clip(session, body.stock)
        except stock.StockError as exc:
            raise ApiError(502, "stock_error", str(exc)) from exc
    else:
        assert body.asset_id is not None
        found = assets.get_asset(session, body.asset_id)
        if found is None:
            raise ApiError(404, "not_found", f"asset {body.asset_id} not found")
        asset = found
    kind = ITEM_KINDS.get(asset.kind)
    if kind is None:
        raise ApiError(
            422, "validation_error", f"asset {asset.id} is a {asset.kind}, not B-roll"
        )
    if kind == "image":
        return asset.id, kind, None
    try:
        return asset.id, kind, probe_media(Path(asset.path)).duration
    except FFmpegError:
        return asset.id, kind, None


def _item(
    item_id: str,
    asset_id: int,
    kind: TrackItemKind,
    span: BrollInsert | TrackItem,
    props: BrollProps,
    seconds: float | None,
) -> TrackItem:
    """Return B-roll item item_id over span's times (pipeline/broll
    broll_item); 422 if the video ends before its offset."""
    try:
        return broll_item(item_id, asset_id, kind, span.start, span.end, props, seconds)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc


def _save(session: Session, row: ClipRow, items: list[TrackItem]) -> Clip:
    """Give row's clip the broll track items and return the clip; 422 if its
    tracks are then not valid."""
    tracks = row.to_model().tracks.model_copy(update={"broll": items})
    return store_tracks(session, row, tracks)
