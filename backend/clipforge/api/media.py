"""Media endpoints (SPEC 7): the project's source video (with HTTP Range) and
its thumbnail; the font library, where TTF and OTF fonts can be uploaded
(SPEC-v2 3.4) to use in caption styles and brand templates; the media
library of images, logos, videos and audio to put on a timeline (SPEC-v2
3.5)."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge import assets, media_library
from clipforge.api.deps import get_engine, project_row
from clipforge.api.errors import ApiError
from clipforge.db import BrandTemplateRow, ClipRow
from clipforge.fonts import (
    MAX_FONT_BYTES,
    FontConflictError,
    FontError,
    font_names,
    store_font,
)
from clipforge.job_rows import process_work_dir
from clipforge.models import (
    MEDIA_LIBRARY_TAG,
    Asset,
    AssetKind,
    FontFile,
    MediaItem,
    MediaMeta,
    MediaTags,
    MediaUpdate,
)
from clipforge.pipeline.step import SOURCE, THUMB, StepError

router = APIRouter()


@router.get("/media/{project_id}/source")
def get_source(
    project_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve the project's source.mp4 (as ingested by its latest process job).

    Starlette's FileResponse answers a Range header with 206 and a
    Content-Range, so the editor can seek; 404 until ingest has run.
    """
    source = _work_file(engine, project_id, SOURCE, "source video")
    return FileResponse(source, media_type="video/mp4")


@router.get("/media/{project_id}/thumbnail")
def get_thumbnail(
    project_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve the project's thumb.jpg (made by ingest); 404 until it exists."""
    thumbnail = _work_file(engine, project_id, THUMB, "thumbnail")
    return FileResponse(thumbnail, media_type="image/jpeg")


@router.get("/fonts")
def list_fonts(engine: Annotated[Engine, Depends(get_engine)]) -> list[FontFile]:
    """Return the fonts of the library, bundled and uploaded, in id order."""
    with Session(engine) as session:
        return [
            _font_file(asset)
            for asset in assets.list_assets(session, kind="font")
            if Path(asset.path).is_file()
        ]


@router.post("/fonts", status_code=201)
def upload_font(
    engine: Annotated[Engine, Depends(get_engine)],
    file: UploadFile,
    license: Annotated[str, Form()] = "user-supplied",
) -> FontFile:
    """Add an uploaded TTF or OTF font to the library; its tables are parsed
    and its names are what a caption style or brand template then calls it.
    422 if the file is not a usable font, 409 if a font has its name."""
    if not (file.filename or "").lower().endswith((".ttf", ".otf")):
        raise ApiError(422, "validation_error", "file: name must end in .ttf or .otf")
    try:
        path, _ = store_font(file.file.read(MAX_FONT_BYTES + 1))
    except FontConflictError as exc:
        raise ApiError(409, "conflict", f"file: {exc}") from exc
    except FontError as exc:
        raise ApiError(422, "validation_error", f"file: {exc}") from exc
    with Session(engine) as session:
        asset = assets.add_asset(
            session,
            "font",
            str(path),
            license.strip() or "user-supplied",
            assets.font_copyright(path),
            tags=[assets.UPLOADED_TAG],
        )
    return _font_file(asset)


@router.delete("/fonts/{asset_id}", status_code=204)
def delete_font(
    asset_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Response:
    """Delete an uploaded font and its file. 404 if there is no such font, 409
    for a bundled font or one that a brand template or a clip's caption style
    uses."""
    with Session(engine) as session:
        asset = assets.get_asset(session, asset_id)
        if asset is None or asset.kind != "font":
            raise ApiError(404, "not_found", f"font {asset_id} not found")
        if assets.UPLOADED_TAG not in asset.tags:
            raise ApiError(409, "conflict", "a bundled font cannot be deleted")
        names = _font_file(asset).names
        if any(_uses(session, name) for name in names):
            raise ApiError(409, "conflict", "a brand template or clip uses this font")
        assets.delete_asset(session, asset_id)
    Path(asset.path).unlink(missing_ok=True)
    return Response(status_code=204)


@router.get("/library")
def list_library(
    engine: Annotated[Engine, Depends(get_engine)],
    kind: AssetKind | None = None,
    tag: str | None = None,
) -> list[MediaItem]:
    """Return the media library's files in id order, only those of kind and
    with the owner's tag if given; a file that is gone from the disk is left
    out."""
    with Session(engine) as session:
        uses = media_library.clip_uses(session)
        found = assets.list_assets(session, kind=kind, tag=MEDIA_LIBRARY_TAG)
    items = []
    for asset in found:
        meta = media_library.read_meta(asset)
        if meta is not None and (tag is None or tag.lower() in asset.tags):
            items.append(media_library.media_item(asset, meta, uses.get(asset.id, [])))
    return items


@router.post("/library", status_code=201)
def upload_media(
    engine: Annotated[Engine, Depends(get_engine)],
    file: UploadFile,
    kind: Annotated[AssetKind | None, Form()] = None,
    license: Annotated[str, Form()] = "user-supplied",
    attribution: Annotated[str, Form()] = "",
    tags: Annotated[list[str] | None, Form()] = None,
) -> MediaItem:
    """Add an uploaded image, video or audio file to the media library.

    The file is sniffed (PNG, JPEG, WebP, GIF, MP4/MOV, WebM/MKV, AVI, MP3,
    WAV, M4A, AAC, OGG, FLAC), ffprobe must read it and a thumbnail is made.
    kind "logo" marks an image as a logo, "music" an audio file as music
    (GET /api/music lists it). 422 if the file is not a usable
    media file or kind or tags are wrong, 409 if the library has it.
    """
    try:
        clean = TypeAdapter(MediaTags).validate_python(tags or [])
    except ValidationError as exc:
        raise ApiError(422, "validation_error", f"tags: {_reason(exc)}") from exc
    try:
        path, chosen, meta = media_library.store_upload(
            file.file, file.filename or "", kind
        )
    except media_library.DuplicateMedia as exc:
        raise ApiError(409, "conflict", f"file: {exc}") from exc
    except media_library.MediaError as exc:
        raise ApiError(422, "validation_error", f"file: {exc}") from exc
    with Session(engine) as session:
        asset = assets.add_asset(
            session,
            chosen,  # type: ignore[arg-type]
            str(path),
            license.strip() or "user-supplied",
            attribution.strip(),
            tags=[MEDIA_LIBRARY_TAG, *clean],
        )
    return media_library.media_item(asset, meta, [])


@router.patch("/library/{asset_id}")
def update_media(
    asset_id: int,
    changes: MediaUpdate,
    engine: Annotated[Engine, Depends(get_engine)],
) -> MediaItem:
    """Change the tags, license or attribution of a media library file.
    404 if there is no such file."""
    with Session(engine) as session:
        asset, meta = _library_file(session, asset_id)
        fields: dict[str, object] = changes.model_dump(exclude_none=True)
        if "tags" in fields:
            fields["tags"] = [MEDIA_LIBRARY_TAG, *(changes.tags or [])]
        asset = assets.update_asset(session, asset_id, **fields)
        uses = media_library.clip_uses(session).get(asset_id, [])
    return media_library.media_item(asset, meta, uses)


@router.delete("/library/{asset_id}", status_code=204)
def delete_media(
    asset_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Response:
    """Delete a media library file and its thumbnail. 404 if there is no
    such file, 409 if a clip's timeline plays it."""
    with Session(engine) as session:
        asset = _library_asset(session, asset_id)
        used = media_library.clip_uses(session).get(asset_id, [])
        if used:
            ids = ", ".join(str(clip_id) for clip_id in used)
            raise ApiError(409, "conflict", f"clips {ids} play this file")
        assets.delete_asset(session, asset_id)
    media_library.delete_files(asset)
    return Response(status_code=204)


@router.get("/library/{asset_id}/file")
def get_media_file(
    asset_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve a media library file (with HTTP Range, so it can be played)."""
    with Session(engine) as session:
        asset, meta = _library_file(session, asset_id)
    return FileResponse(asset.path, media_type=meta.mime, filename=meta.name)


@router.get("/library/{asset_id}/thumbnail")
def get_media_thumbnail(
    asset_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve the thumbnail of a media library file: the picture, a frame of
    the video or the waveform of the audio."""
    with Session(engine) as session:
        asset, meta = _library_file(session, asset_id)
    thumb = media_library.thumbnail_path(asset, meta)
    if thumb is None:
        raise ApiError(404, "not_found", f"file {asset_id} has no thumbnail")
    return FileResponse(thumb)


def _library_asset(session: Session, asset_id: int) -> Asset:
    """Return the media library asset asset_id; 404 if there is none."""
    asset = assets.get_asset(session, asset_id)
    if asset is None or not media_library.is_library_asset(asset):
        raise ApiError(404, "not_found", f"media file {asset_id} not found")
    return asset


def _library_file(session: Session, asset_id: int) -> tuple[Asset, MediaMeta]:
    """Return the media library asset asset_id and the info next to its file;
    404 if there is no such asset or its file is gone."""
    asset = _library_asset(session, asset_id)
    meta = media_library.read_meta(asset)
    if meta is None:
        raise ApiError(404, "not_found", f"the file of {asset_id} is missing")
    return asset, meta


def _reason(exc: ValidationError) -> str:
    """Return the first problem of a validation error, as a sentence."""
    return str(exc.errors()[0]["msg"]).removeprefix("Value error, ")


def _font_file(asset: Asset) -> FontFile:
    """Return the library entry of the font asset."""
    names = sorted(font_names(Path(asset.path)))
    return FontFile(
        asset=asset, names=names, bundled=assets.UPLOADED_TAG not in asset.tags
    )


def _uses(session: Session, font: str) -> bool:
    """Return whether a brand template or a clip's caption style names font."""
    templates = select(BrandTemplateRow).where(col(BrandTemplateRow.font) == font)
    if session.exec(templates).first() is not None:
        return True
    return any(row.caption_style.font == font for row in session.exec(select(ClipRow)))


def _work_file(engine: Engine, project_id: int, name: str, what: str) -> Path:
    """Return file `name` of the project's latest process job.

    Raises the 404 ApiError if the project, its job or the file is missing.
    """
    with Session(engine) as session:
        project_row(session, project_id)
        try:
            path: Path = process_work_dir(session, project_id) / name
        except StepError as exc:
            raise ApiError(404, "not_found", str(exc)) from exc
    if not path.is_file():
        raise ApiError(
            404, "not_found", f"the {what} of project {project_id} is not ready"
        )
    return path
