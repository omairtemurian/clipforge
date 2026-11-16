"""Covers (thumbnails) of a clip's posts (SPEC-v2 3.10): a frame of the
rendered video picked at a time, or an image the owner uploads, saved as an
image Asset and applied to the clip's posts.

The files live in {data_dir}/output/{project_id}/covers. JPEG and PNG are
taken, at most 8 MB: the smallest of the platforms' limits (YouTube
thumbnails.set 50 MB, Instagram Reels cover 8 MB, JPEG; docs/decisions.md,
TASK-148). TikTok takes no cover image (only a frame time) and Instagram
only a public URL, so their publishers ignore the file for now.
"""

import hashlib
import tempfile
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, select

from clipforge import assets, ffmpeg, posts
from clipforge.asset_rows import AssetRow
from clipforge.models import Asset, Clip, Post
from clipforge.pipeline.render import project_output

COVERS_DIRNAME = "covers"
UPLOAD_MAX_BYTES = 8 * 1024 * 1024
THUMBNAIL_TAG = "thumbnail"
FRAME_LICENSE = "Frame of the clip"
UPLOAD_LICENSE = "Uploaded by the owner"
IMAGE_TYPES: dict[bytes, str] = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
}


class ThumbnailError(ValueError):
    """A cover cannot be made; the message says why."""


class NotRendered(ThumbnailError):
    """The clip has no rendered video to take a frame from."""


def covers_dir(project_id: int) -> Path:
    """Return the directory of a project's covers."""
    return project_output(project_id) / COVERS_DIRNAME


def clip_tag(clip_id: int) -> str:
    """Return the tag that marks the covers of a clip."""
    return f"clip-{clip_id}"


def rendered_video(clip: Clip) -> Path:
    """Return the clip's rendered video; ThumbnailError if it is not
    rendered."""
    path = Path(clip.output_path) if clip.output_path else None
    if clip.status != "rendered" or path is None or not path.is_file():
        raise NotRendered("Render the clip first: covers are frames of its video.")
    return path


def check_time(video: Path, time_s: float) -> None:
    """ThumbnailError if the video has no frame at time_s seconds."""
    duration = ffmpeg.probe_media(video).duration
    if time_s >= duration:
        raise ThumbnailError(
            f"The clip lasts {duration:.1f} s: pick a time before its end."
        )


def frame_jpeg(clip: Clip, time_s: float) -> bytes:
    """Return the JPEG of the clip's rendered video at time_s seconds (the
    frame picker's preview; nothing is saved). ThumbnailError if the clip
    is not rendered or ends before time_s."""
    video = rendered_video(clip)
    check_time(video, time_s)
    with tempfile.TemporaryDirectory() as folder:
        frame = ffmpeg.extract_frame(video, Path(folder) / "frame.jpg", time_s)
        return frame.read_bytes()


def save_frame(engine: Engine, clip: Clip, time_s: float) -> Asset:
    """Save the frame of the clip's rendered video at time_s seconds as an
    image asset and return it (the same asset when that millisecond was
    saved before). ThumbnailError if the clip is not rendered or ends
    before time_s."""
    video = rendered_video(clip)
    check_time(video, time_s)
    path = covers_dir(clip.project_id) / f"{clip.id}-{round(time_s * 1000)}ms.jpg"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg.extract_frame(video, path, time_s)
    return _asset(engine, clip, path, FRAME_LICENSE, "frame")


def save_upload(engine: Engine, clip: Clip, data: bytes) -> Asset:
    """Save an uploaded JPEG or PNG as an image asset of the clip and
    return it; ThumbnailError if data is empty, over 8 MB or no JPEG/PNG."""
    if not data:
        raise ThumbnailError("The image is empty.")
    if len(data) > UPLOAD_MAX_BYTES:
        raise ThumbnailError("The image is over 8 MB.")
    suffix = next(
        (ext for magic, ext in IMAGE_TYPES.items() if data.startswith(magic)), None
    )
    if suffix is None:
        raise ThumbnailError("The cover must be a JPEG or PNG image.")
    digest = hashlib.sha256(data).hexdigest()[:16]
    path = covers_dir(clip.project_id) / f"{clip.id}-upload-{digest}{suffix}"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return _asset(engine, clip, path, UPLOAD_LICENSE, "upload")


def image_asset(engine: Engine, asset_id: int) -> Asset:
    """Return the image asset asset_id; ThumbnailError if there is none or
    it is no image."""
    with Session(engine) as session:
        asset = assets.get_asset(session, asset_id)
    if asset is None or asset.kind != "image":
        raise ThumbnailError(f"There is no image asset {asset_id}.")
    return asset


def apply_to_all(engine: Engine, clip_id: int, asset_id: int) -> list[Post]:
    """Make the image asset the cover of every draft and queued post of the
    clip and return those posts (posts that were sent meanwhile keep
    theirs). ThumbnailError if the asset is no image."""
    image_asset(engine, asset_id)
    changed = []
    for post in posts.list_posts(engine, clip_id=clip_id):
        if post.status not in posts.EDITABLE:
            continue
        try:
            changed.append(
                posts.update_post(engine, post.id, thumbnail_asset_id=asset_id)
            )
        except posts.PostLocked:
            continue
    return changed


def _asset(engine: Engine, clip: Clip, path: Path, license: str, tag: str) -> Asset:
    """Return the asset of the file at path, added if it has none yet."""
    with Session(engine) as session:
        known = session.exec(select(AssetRow).where(AssetRow.path == str(path))).first()
        if known is not None:
            return known.to_model()
        return assets.add_asset(
            session,
            "image",
            str(path),
            license,
            tags=[THUMBNAIL_TAG, tag, clip_tag(clip.id)],
        )
