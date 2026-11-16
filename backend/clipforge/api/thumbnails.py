"""Cover endpoints of a clip's posts (SPEC-v2 3.10): pick a frame of the
rendered video or upload an image, and apply it to the clip's posts.

    GET  /clips/{id}/frame?t=       -> JPEG of the rendered video at t seconds
    POST /clips/{id}/thumbnail      ThumbnailFrame -> Asset (the frame saved)
    POST /clips/{id}/thumbnail/upload   image bytes (JPEG/PNG) -> Asset
    POST /clips/{id}/thumbnail/apply    ThumbnailApply -> [Post] (draft and
                                    queued posts of the clip get the cover)
    GET  /thumbnails/{asset_id}     -> the image of a cover asset
"""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import thumbnails
from clipforge.api.deps import clip_row, get_engine
from clipforge.api.errors import ApiError, not_found
from clipforge.ffmpeg import FFmpegError
from clipforge.models import Asset, Clip, Post, ThumbnailApply, ThumbnailFrame

router = APIRouter()
T = TypeVar("T")

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("/clips/{clip_id}/frame")
def get_frame(
    clip_id: int, engine: EngineDep, t: Annotated[float, Query(ge=0)] = 0
) -> Response:
    """Return the JPEG of the clip's rendered video t seconds from its start
    (the frame picker's preview); 409 if the clip is not rendered, 422 if
    it ends before t."""
    clip = _clip(engine, clip_id)
    jpeg = _covers(lambda: thumbnails.frame_jpeg(clip, t))
    return Response(jpeg, media_type="image/jpeg")


@router.post("/clips/{clip_id}/thumbnail", status_code=201)
def pick_frame(clip_id: int, body: ThumbnailFrame, engine: EngineDep) -> Asset:
    """Save the frame at body.time_s as an image asset (the cover to give
    the posts); the same asset again for the same millisecond."""
    clip = _clip(engine, clip_id)
    return _covers(lambda: thumbnails.save_frame(engine, clip, body.time_s))


@router.post("/clips/{clip_id}/thumbnail/upload", status_code=201)
async def upload_cover(clip_id: int, request: Request, engine: EngineDep) -> Asset:
    """Save the uploaded JPEG or PNG (the request body, at most 8 MB) as an
    image asset; 422 for any other file."""
    clip = _clip(engine, clip_id)
    data = await _body(request)
    return _covers(lambda: thumbnails.save_upload(engine, clip, data))


@router.post("/clips/{clip_id}/thumbnail/apply")
def apply_cover(clip_id: int, body: ThumbnailApply, engine: EngineDep) -> list[Post]:
    """Make the image asset the cover of every draft and queued post of the
    clip; 422 if the asset is no image."""
    _clip(engine, clip_id)
    return _covers(lambda: thumbnails.apply_to_all(engine, clip_id, body.asset_id))


@router.get("/thumbnails/{asset_id}")
def get_cover(asset_id: int, engine: EngineDep) -> FileResponse:
    """Serve the image of a cover asset; 404 if it has none."""
    try:
        asset = thumbnails.image_asset(engine, asset_id)
    except thumbnails.ThumbnailError as exc:
        raise not_found("cover", asset_id) from exc
    path = Path(asset.path)
    if not path.is_file():
        raise not_found("cover", asset_id)
    return FileResponse(path)


def _clip(engine: Engine, clip_id: int) -> Clip:
    """Return the clip; 404 if there is none."""
    with Session(engine) as session:
        return clip_row(session, clip_id).to_model()


async def _body(request: Request) -> bytes:
    """Read the request body, refusing more than the upload limit."""
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > thumbnails.UPLOAD_MAX_BYTES:
            raise ApiError(422, "validation_error", "The image is over 8 MB.")
    return bytes(data)


def _covers(make: Callable[[], T]) -> T:
    """Run make; a cover that cannot be made is 409 if the clip is not
    rendered, else 422."""
    try:
        return make()
    except thumbnails.NotRendered as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    except (thumbnails.ThumbnailError, FFmpegError) as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
