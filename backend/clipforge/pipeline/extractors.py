"""Which video links yt-dlp can download (SPEC-v2 3.1).

The answer comes from the extractors of the installed yt-dlp, so a site that
a yt-dlp update adds (or drops) is picked up without a change here. Vimeo and
Zoom recordings are supported this way, as far as their extractors go.
"""

from urllib.parse import urlsplit

from yt_dlp.extractor import list_extractor_classes
from yt_dlp.utils import MEDIA_EXTENSIONS

from clipforge.pipeline.step import StepError

GENERIC = "generic"
DIRECT_MEDIA_EXTENSIONS = frozenset(
    MEDIA_EXTENSIONS.video + MEDIA_EXTENSIONS.audio + MEDIA_EXTENSIONS.manifests
)


class UnsupportedSource(StepError):
    """The link is to a site that no yt-dlp extractor handles."""


def extractor_for(url: str) -> str | None:
    """Return the name of the site-specific extractor of the installed yt-dlp
    that matches url, or None if only the generic one does.

    Extractors that yt-dlp marks as not working (_WORKING False) are skipped.
    """
    for extractor in list_extractor_classes():
        name = str(extractor.IE_NAME)
        if name == GENERIC or not extractor.working():
            continue
        if extractor.suitable(url):
            return name
    return None


def is_direct_media(url: str) -> bool:
    """Return True if the path of url ends in a video, audio or stream
    manifest extension, which yt-dlp's generic extractor downloads as it is."""
    name = urlsplit(url).path.rsplit("/", 1)[-1]
    return name.rpartition(".")[2].lower() in DIRECT_MEDIA_EXTENSIONS


def require_supported(url: str) -> str:
    """Return the extractor name of url ("generic" for a direct media link).

    Raises UnsupportedSource if no extractor of the installed yt-dlp handles
    url: a page of an unknown site cannot be downloaded from.
    """
    name = extractor_for(url)
    if name is not None:
        return name
    if is_direct_media(url):
        return GENERIC
    host = urlsplit(url).hostname or url
    raise UnsupportedSource(
        f"{host} is not a supported video site. Link to a video page of a site "
        "that yt-dlp supports (YouTube, Vimeo, Zoom recordings, ...) or a direct "
        "video file, or upload the file."
    )
