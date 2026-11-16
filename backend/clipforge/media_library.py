"""The media library (SPEC-v2 3.5): images, logos, videos and audio that the
owner uploads, to put on a clip's timeline as B-roll, overlays or sound.

Each upload is an Asset tagged MEDIA_LIBRARY_TAG, kept in its own directory
{data_dir}/media/<hash of its bytes>/ with the file (file.<ext>, never named
by the client), its thumbnail and info.json (MediaMeta). The file is sniffed
by its first bytes (media_sniff) and ffprobe must read the kind of stream it
should hold, so a renamed or truncated file is refused. An upload is staged in
a temporary directory first: a refused file changes nothing.
"""

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO

from sqlmodel import Session, col, select

from clipforge import config
from clipforge.db import ClipRow
from clipforge.ffmpeg import FFmpegError, ffprobe_json, run_ffmpeg
from clipforge.media_sniff import HEAD_BYTES, mime_type, sniff
from clipforge.models import MEDIA_LIBRARY_TAG, Asset, MediaItem, MediaMeta
from clipforge.timeline import TRACK_ITEM_KINDS

MEDIA_DIRNAME = "media"
INFO_NAME = "info.json"
THUMB_WIDTH = 320
WAVE_HEIGHT = 80
WAVE_COLOR = "0x6366f1"
MAX_BYTES = {"image": 25 * 1024**2, "audio": 300 * 1024**2, "video": 2 * 1024**3}
CHUNK_BYTES = 1024 * 1024
NAME_MAX = 120
# The asset kinds an upload may be given, by what it is.
KINDS = {
    "image": ("image", "logo"),
    "video": ("video",),
    "audio": ("audio", "music"),
}


class MediaError(ValueError):
    """An upload is refused; the message says why."""


class DuplicateMedia(MediaError):
    """The library already holds the file."""

    def __init__(self) -> None:
        super().__init__("this file is already in the media library")


def media_root() -> Path:
    """Return the directory of the library's files."""
    return config.settings.data_dir / MEDIA_DIRNAME


def is_library_asset(asset: Asset) -> bool:
    """Return whether asset is a media library upload."""
    return MEDIA_LIBRARY_TAG in asset.tags


def user_tags(asset: Asset) -> list[str]:
    """Return the tags of asset that the owner set."""
    return [tag for tag in asset.tags if tag != MEDIA_LIBRARY_TAG]


def store_upload(
    source: BinaryIO, filename: str, kind: str | None = None
) -> tuple[Path, str, MediaMeta]:
    """Validate the uploaded file in source and store it in the library.

    kind may name the asset kind the owner wants: "logo" for an image,
    "music" for audio (the music library lists it), else only what the file
    is. Returns the stored file, its asset kind and its
    MediaMeta. Raises MediaError if the file is empty, not an image, video or
    audio file, too big, not readable by ffprobe, or of another kind than
    kind, and DuplicateMedia if the library has it; nothing is stored then.
    """
    root = media_root()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".upload-", dir=root) as temp:
        staging = Path(temp)
        digest, size, suffix, is_image = _stage(source, staging)
        staged = staging / f"file{suffix}"
        found, info = _inspect(staged, is_image)
        chosen = _chosen_kind(found, kind)
        limit = MAX_BYTES[found]
        if size > limit:
            raise MediaError(f"a {found} file is at most {_size_text(limit)}")
        meta = MediaMeta(
            name=_clean_name(filename),
            mime=mime_type(suffix, found),
            size_bytes=size,
            **info,
        )
        meta.thumbnail = _make_thumbnail(staged, chosen, meta.duration)
        (staging / INFO_NAME).write_text(meta.model_dump_json())
        target = root / digest
        if target.exists():
            raise DuplicateMedia
        os.replace(staging, target)
    return target / staged.name, chosen, meta


def read_meta(asset: Asset) -> MediaMeta | None:
    """Return the MediaMeta next to the file of asset, or None if the file or
    its info is missing or unreadable."""
    path = Path(asset.path)
    try:
        info = json.loads((path.parent / INFO_NAME).read_text())
        meta = MediaMeta.model_validate(info)
    except (OSError, ValueError):
        return None
    return meta if path.is_file() else None


def thumbnail_path(asset: Asset, meta: MediaMeta) -> Path | None:
    """Return the thumbnail file of asset, or None if it has none."""
    if meta.thumbnail is None:
        return None
    path = Path(asset.path).parent / meta.thumbnail
    return path if path.is_file() else None


def media_item(asset: Asset, meta: MediaMeta, clip_ids: list[int]) -> MediaItem:
    """Return the library entry of asset, which clip_ids use."""
    return MediaItem(
        asset=asset,
        tags=user_tags(asset),
        name=meta.name,
        mime=meta.mime,
        size_bytes=meta.size_bytes,
        duration=meta.duration,
        width=meta.width,
        height=meta.height,
        has_thumbnail=thumbnail_path(asset, meta) is not None,
        used_in_clips=clip_ids,
    )


def clip_uses(session: Session) -> dict[int, list[int]]:
    """Map each asset id that a clip's timeline plays to the ids of those
    clips, in id order."""
    uses: dict[int, list[int]] = {}
    for clip in session.exec(select(ClipRow).order_by(col(ClipRow.id))):
        for track in TRACK_ITEM_KINDS:
            for item in getattr(clip.tracks, track):
                if item.asset_id is not None and clip.id is not None:
                    ids = uses.setdefault(item.asset_id, [])
                    if clip.id not in ids:
                        ids.append(clip.id)
    return uses


def delete_files(asset: Asset) -> None:
    """Delete the directory of the library file of asset."""
    directory = Path(asset.path).parent
    if directory.parent == media_root():
        shutil.rmtree(directory, ignore_errors=True)


def _stage(source: BinaryIO, staging: Path) -> tuple[str, int, str, bool]:
    """Copy source into staging as file<suffix>; return the first 16 hex
    digits of the SHA-256 of its bytes, its size, the suffix its first bytes
    call for and whether it is an image. Stops at the size limit."""
    head = source.read(HEAD_BYTES)
    if not head:
        raise MediaError("the file is empty")
    sniffed = sniff(head)
    if sniffed is None:
        raise MediaError("not an image (PNG, JPEG, WebP, GIF), video or audio file")
    limit = MAX_BYTES["image" if sniffed.image else "video"]
    digest = hashlib.sha256(head)
    size = len(head)
    with (staging / f"file{sniffed.suffix}").open("wb") as out:
        out.write(head)
        for chunk in _chunks(source):
            size += len(chunk)
            if size > limit:
                raise MediaError(f"the file is over {_size_text(limit)}")
            digest.update(chunk)
            out.write(chunk)
    return digest.hexdigest()[:16], size, sniffed.suffix, sniffed.image


def _size_text(size: int) -> str:
    """Return size in bytes as "<n> MB", or as bytes if it is under 1 MB."""
    return f"{size // 1024**2} MB" if size >= 1024**2 else f"{size} bytes"


def _chunks(source: BinaryIO) -> Iterator[bytes]:
    """Yield the rest of source in chunks."""
    while chunk := source.read(CHUNK_BYTES):
        yield chunk


def _inspect(path: Path, is_image: bool) -> tuple[str, dict[str, Any]]:
    """Return what ffprobe finds in the file at path: "image", "video" or
    "audio", and the MediaMeta fields it gives (duration, width, height).

    Raises MediaError if ffprobe cannot read it or it holds no picture
    (image), no video stream, or no audio stream or no length (video, audio).
    """
    try:
        report = ffprobe_json(path)
    except (FFmpegError, ValueError) as exc:
        raise MediaError("the file cannot be read as media") from exc
    streams: list[dict[str, Any]] = report.get("streams", [])
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
            and not s.get("disposition", {}).get("attached_pic", 0)
        ),
        None,
    )
    if is_image:
        if video is None or not video.get("width") or not video.get("height"):
            raise MediaError("the image has no picture")
        return "image", {"width": int(video["width"]), "height": int(video["height"])}
    duration = _seconds(report.get("format", {}), video)
    if duration is None:
        raise MediaError("the file has no length: it is not a playable video or audio")
    if video is not None:
        size = {"width": int(video["width"]), "height": int(video["height"])}
        return "video", {"duration": duration, **size}
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise MediaError("the file has no video or audio stream")
    return "audio", {"duration": duration}


def _seconds(fmt: dict[str, Any], video: dict[str, Any] | None) -> float | None:
    """Return the container's duration, else the video stream's, if positive."""
    for section in (fmt, video or {}):
        try:
            seconds = float(section["duration"])
        except (KeyError, ValueError):
            continue
        if seconds > 0:
            return seconds
    return None


def _chosen_kind(found: str, kind: str | None) -> str:
    """Return the asset kind of a file that is `found`, which kind (or None)
    asked for; MediaError if the file cannot be that."""
    if kind is None:
        return found
    if kind not in KINDS[found]:
        raise MediaError(f"the file is a {found}, not a {kind}")
    return kind


def _clean_name(filename: str) -> str:
    """Return the file name the client gave without its directories, cut to
    NAME_MAX characters ("file" if it has none)."""
    name = Path(filename.replace("\\", "/")).name.strip()
    return (name or "file")[:NAME_MAX]


def _make_thumbnail(path: Path, kind: str, duration: float | None) -> str:
    """Draw the thumbnail of the file at path next to it and return its name:
    the picture of an image or logo (PNG, so transparency stays), a frame of
    a video, the waveform of audio (PNG). Raises MediaError if ffmpeg fails."""
    scale = f"scale=w='min({THUMB_WIDTH},iw)':h=-2"
    args: list[str | Path]
    if kind in ("image", "logo"):
        name, args = "thumb.png", ["-i", path, "-vf", scale]
    elif kind == "video":
        name = "thumb.jpg"
        at = min(1.0, (duration or 0) / 2)
        args = ["-ss", f"{at:.3f}", "-i", path, "-vf", scale, "-q:v", "3"]
    else:
        wave = f"showwavespic=s={THUMB_WIDTH}x{WAVE_HEIGHT}:colors={WAVE_COLOR}"
        name, args = "thumb.png", ["-i", path, "-filter_complex", wave]
    try:
        run_ffmpeg([*args, "-frames:v", "1", "-update", "1", path.parent / name])
    except FFmpegError as exc:
        raise MediaError("no thumbnail can be made of the file") from exc
    return name
