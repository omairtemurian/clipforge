"""Music library endpoints (SPEC-v2 3.5): the bundled CC0 loops
(assets/music, pipeline/music) and the music files uploaded to the media
library (POST /api/library with kind "music"), to put on a clip's music
track (PUT /api/clips/{id}/tracks: volume, fades and ducking are the
item's props, models.MusicProps), and their files, to listen to."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import assets, media_library
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError
from clipforge.ffmpeg import FFmpegError, ffprobe_json
from clipforge.models import Asset, MusicTrack
from clipforge.pipeline.music import bundled_track

router = APIRouter()
# The MIME types of the bundled loops' files, by suffix.
BUNDLED_MIME = {".flac": "audio/flac"}


@router.get("/music")
def list_music(
    engine: Annotated[Engine, Depends(get_engine)], tag: str | None = None
) -> list[MusicTrack]:
    """Return the music library, bundled loops first, then uploads, each in
    id order, only those with tag (a mood or the owner's tag) if given; a
    track whose file is gone is left out."""
    with Session(engine) as session:
        found = assets.list_assets(session, kind="music")
    tracks = [track for asset in found if (track := music_track(asset)) is not None]
    tracks.sort(key=lambda track: not track.bundled)
    if tag is None:
        return tracks
    return [track for track in tracks if tag.lower() in track.tags]


@router.get("/music/{asset_id}/file")
def get_music_file(
    asset_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Serve a music library file (with HTTP Range, so it can be played).
    404 if there is no such music or its file is gone."""
    with Session(engine) as session:
        asset = assets.get_asset(session, asset_id)
    track = None if asset is None or asset.kind != "music" else music_track(asset)
    if asset is None or track is None:
        raise ApiError(404, "not_found", f"music {asset_id} not found")
    meta = media_library.read_meta(asset)
    mime = meta.mime if meta is not None else BUNDLED_MIME.get(Path(asset.path).suffix)
    return FileResponse(asset.path, media_type=mime or "application/octet-stream")


def music_track(asset: Asset) -> MusicTrack | None:
    """Return the music library entry of the music asset, or None if its
    file is gone: a bundled loop has its catalogue title and moods, an
    upload its file name and the owner's tags."""
    path = Path(asset.path)
    if not path.is_file():
        return None
    bundled = bundled_track(path) if assets.BUNDLED_TAG in asset.tags else None
    if bundled is not None:
        title, tags = bundled.title, list(bundled.tags)
    elif media_library.is_library_asset(asset):
        meta = media_library.read_meta(asset)
        if meta is None:
            return None
        title, tags = meta.name, media_library.user_tags(asset)
    else:
        title, tags = path.name, list(asset.tags)
    return MusicTrack(
        asset=asset,
        title=title,
        duration=_duration(str(path), path.stat().st_mtime_ns),
        bundled=bundled is not None,
        tags=tags,
    )


@lru_cache(maxsize=256)
def _duration(path: str, mtime_ns: int) -> float | None:
    """Return how many seconds the sound file at path lasts, as ffprobe
    reads it (cached while the file is unchanged); None if it cannot."""
    try:
        return float(ffprobe_json(Path(path))["format"]["duration"])
    except (FFmpegError, KeyError, ValueError):
        return None
