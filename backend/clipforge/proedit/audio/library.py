"""Audio files of the owner in the Pro Edit library (SPEC-v3 1.2, 5.2, 5.3):
a file downloaded from Pixabay and an upload of the owner's own.

store_audio checks the file like any media upload (a sniffed audio file that
ffprobe reads, within the size limit, stored once by its content in the media
directory), adds it to the asset library as music, sfx or audio with its
license, credit, source URL and time, and tags it (tagging.tag_asset). A file
that cannot be analyzed is not kept.
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal

from sqlmodel import Session

from clipforge import assets, media_library
from clipforge.ffmpeg import FFmpegError
from clipforge.media_library import DuplicateMedia, MediaError
from clipforge.models import Asset
from clipforge.pipeline.step import StepError
from clipforge.proedit.audio.tagging import tag_asset

# Why the owner may use their own upload; "other" is not enough to be sure.
AudioRights = Literal["own", "permission", "cc_by", "public_domain"]
RIGHTS_LABELS: dict[str, str] = {
    "own": "Own work",
    "permission": "Used with permission",
    "cc_by": "CC BY",
    "public_domain": "Public domain",
}
UPLOAD_TAG = "own-upload"


class AudioFileError(ValueError):
    """An audio file or its rights are refused; the message says why."""


class DuplicateAudio(AudioFileError):
    """The library already has the file."""


def store_audio(
    session: Session,
    source: BinaryIO,
    filename: str,
    *,
    kind: Literal["sfx", "music", "audio"],
    license: str,
    attribution: str,
    source_url: str | None,
    tags: list[str],
    category: str | None = None,
) -> Asset:
    """Store the audio file in source in the library and return its asset,
    analyzed and tagged (kind, category if given).

    Raises DuplicateAudio if the library has the file, AudioFileError if it
    is not an audio file, too big or cannot be analyzed; nothing is kept
    then.
    """
    try:
        path, _, _ = media_library.store_upload(
            source, filename, "music" if kind == "music" else "audio"
        )
    except DuplicateMedia as exc:
        raise DuplicateAudio(str(exc)) from exc
    except MediaError as exc:
        raise AudioFileError(str(exc)) from exc
    try:
        asset = assets.add_asset(
            session,
            kind,
            str(path),
            license,
            attribution=attribution,
            source_url=source_url,
            tags=tags,
        )
    except Exception:
        _discard(path)
        raise
    try:
        assets.update_asset(session, asset.id, downloaded_at=datetime.now(UTC))
        return tag_asset(session, asset, category=category)
    except (StepError, FFmpegError) as exc:
        assets.delete_asset(session, asset.id)
        _discard(path)
        raise AudioFileError(f"the audio cannot be analyzed: {exc}") from exc


def store_own_upload(
    session: Session,
    source: BinaryIO,
    filename: str,
    *,
    rights: AudioRights,
    kind: Literal["sfx", "music", "audio"] = "sfx",
    attribution: str = "",
    category: str | None = None,
) -> Asset:
    """Store an audio file the owner uploads, with the grounds (rights) on
    which they may use it as its license. CC BY needs the credit text.
    Raises AudioFileError for a missing credit and what store_audio raises."""
    credit = attribution.strip()
    if rights == "cc_by" and not credit:
        raise AudioFileError("a CC BY file needs its credit (attribution)")
    return store_audio(
        session,
        source,
        filename,
        kind=kind,
        license=RIGHTS_LABELS[rights],
        attribution=credit,
        source_url=None,
        tags=[assets.UPLOADED_TAG, UPLOAD_TAG],
        category=category,
    )


def _discard(path: Path) -> None:
    """Delete the stored library file at path and its directory."""
    shutil.rmtree(path.parent, ignore_errors=True)
