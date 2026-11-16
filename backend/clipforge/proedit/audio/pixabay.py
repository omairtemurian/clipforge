"""Pixabay music and sound effects in the Pro Edit library (SPEC-v3 1.2, 5.2).

Pixabay's official API serves images and videos only: its documentation
(https://pixabay.com/api/docs/, read 2026-11-04) lists "Search Images" and
"Search Videos" and no audio resource, and /api/audio/ answers the image
search. So there is no PIXABAY_API_KEY audio integration; the owner
downloads a file on pixabay.com/music or /sound-effects and imports it here
with the page URL and a confirmation that it is under the Pixabay Content
License (https://pixabay.com/service/license-summary/: free to use, no
credit needed, not to be sold or distributed on its own). import_pixabay_file
checks the URL (https, pixabay.com, a /music/ or /sound-effects/ page: the
page says whether it is music or an effect) and the confirmation, and
stores the file with license "Pixabay Content License", the page URL, the
download time and a credit line, as every audio asset has.
"""

from pathlib import PurePosixPath
from typing import BinaryIO, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel
from sqlmodel import Session

from clipforge.models import Asset
from clipforge.proedit.audio.library import AudioFileError, store_audio

PIXABAY_LICENSE = "Pixabay Content License"
HOSTS = ("pixabay.com", "www.pixabay.com")
SECTIONS: dict[str, Literal["music", "sfx"]] = {
    "music": "music",
    "sound-effects": "sfx",
}
TAG = "pixabay"
NAME_MAX = 120
API_MESSAGE = (
    "Pixabay's API serves images and videos only, not music or sound effects: "
    "download the file on pixabay.com and import it here with its page URL"
)


class PixabayStatus(BaseModel):
    """How Pixabay audio gets into the library: by import, not by API."""

    api: bool
    message: str


def status() -> PixabayStatus:
    """Return that Pixabay audio is imported by hand, and why."""
    return PixabayStatus(api=False, message=API_MESSAGE)


def audio_kind(source_url: str) -> Literal["music", "sfx"]:
    """Return "music" or "sfx" for the URL of a Pixabay music or sound
    effect page. Raises AudioFileError for any other URL (not https, not
    pixabay.com, not a /music/ or /sound-effects/ page)."""
    parts = urlsplit(source_url.strip())
    segments = [s for s in PurePosixPath(parts.path).parts if s != "/"]
    if (
        parts.scheme != "https"
        or parts.hostname not in HOSTS
        or len(segments) < 2
        or segments[0] not in SECTIONS
    ):
        raise AudioFileError(
            "source_url must be the https://pixabay.com/music/... or "
            "https://pixabay.com/sound-effects/... page of the file"
        )
    return SECTIONS[segments[0]]


def import_pixabay_file(
    session: Session,
    source: BinaryIO,
    filename: str,
    *,
    source_url: str,
    license_confirmed: bool,
    title: str = "",
    category: str | None = None,
) -> Asset:
    """Store a file downloaded from Pixabay (source_url is its page) in the
    library as music or sfx by that page, analyzed and tagged; return its
    asset. title names it in the credit (the file name without extension if
    empty).

    Raises AudioFileError if license_confirmed is False, the URL is not a
    Pixabay audio page or the file is not usable audio; DuplicateAudio if
    the library has the file. Nothing is kept then.
    """
    if not license_confirmed:
        raise AudioFileError(
            f"confirm that the file is under the {PIXABAY_LICENSE} "
            "(license_confirmed must be true)"
        )
    kind = audio_kind(source_url)
    url = source_url.strip()
    name = (title.strip() or PurePosixPath(filename.replace("\\", "/")).stem)[
        :NAME_MAX
    ] or "Pixabay audio"
    return store_audio(
        session,
        source,
        filename,
        kind=kind,
        license=PIXABAY_LICENSE,
        attribution=f'"{name}" on Pixabay ({url}), {PIXABAY_LICENSE}',
        source_url=url,
        tags=[TAG],
        category=category,
    )
