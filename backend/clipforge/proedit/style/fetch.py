"""Fetching a style reference to analyze it, then deleting it (SPEC-v3 1.4,
4.1, 4.2).

A reference is one video link the owner pasted into a style recipe. Its
media is downloaded with the yt-dlp module of the ingest step into
{data_dir}/work/style_<reference id>/ (at most MAX_SECONDS long and
MAX_HEIGHT high), handed to an analyzer, and the directory is removed in a
`finally` block, so it is gone after a success and after a failure of the
download, the checks or the analyzer. Only what the analyzer returns (numbers
and text) outlives the call.
"""

import logging
import shutil
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from clipforge import config
from clipforge.config import Settings
from clipforge.ffmpeg import FFmpegError, probe_media
from clipforge.pipeline import download
from clipforge.pipeline.download import is_url
from clipforge.pipeline.extractors import require_supported
from clipforge.pipeline.step import WORK_DIRNAME, StepError

MAX_LINKS = 5
MAX_SECONDS = 180
MAX_HEIGHT = 720
# The best video stream up to 720p plus the best audio stream, or else the
# best single file up to 720p (the selector of the ingest step, 720p).
STYLE_FORMAT = f"bv*[height<={MAX_HEIGHT}]+ba/b[height<={MAX_HEIGHT}]"
RIGHTS_NOTICE = (
    "Downloading videos may break the site's terms; use only references "
    "you have the right to analyze."
)

logger = logging.getLogger(__name__)
T = TypeVar("T")

_active: set[int] = set()
_active_lock = threading.Lock()


class StyleFetchError(StepError):
    """A style reference cannot be fetched or is over a limit."""


class ReferenceBusy(StyleFetchError):
    """A style reference is being fetched by another call already."""


def style_dir(reference_id: int, cfg: Settings | None = None) -> Path:
    """Return the directory of the media of reference reference_id:
    {data_dir}/work/style_<id>."""
    data_dir = (config.settings if cfg is None else cfg).data_dir
    return data_dir / WORK_DIRNAME / f"style_{reference_id}"


def validate_links(urls: Iterable[str]) -> list[str]:
    """Return the links of a recipe: stripped, without repeats, in order.

    Raises ValueError if there is no link or more than MAX_LINKS, a link is
    not an http(s) URL, or no installed yt-dlp extractor handles it.
    """
    links = list(dict.fromkeys(url.strip() for url in urls))
    if not links or "" in links:
        raise ValueError("a style recipe needs at least one link")
    if len(links) > MAX_LINKS:
        raise ValueError(f"a style recipe takes at most {MAX_LINKS} links")
    for link in links:
        if not is_url(link):
            raise ValueError(f"{link} is not an http(s) link")
        try:
            require_supported(link)
        except StepError as exc:
            raise ValueError(str(exc)) from exc
    return links


def analyze_reference(url: str, reference_id: int, analyzer: Callable[[Path], T]) -> T:
    """Download the video at url, return analyzer(video file) and delete the
    media, even when a step fails.

    Raises StyleFetchError if the video is longer than MAX_SECONDS or higher
    than MAX_HEIGHT, ReferenceBusy if reference reference_id is already being
    fetched; StepError if the download fails; and whatever the analyzer raises.
    """
    with _exclusive(reference_id):
        directory = style_dir(reference_id)
        try:
            _clear(directory)
            directory.mkdir(parents=True)
            info = download.probe(url)
            if info.duration is not None and info.duration > MAX_SECONDS:
                raise StyleFetchError(_too_long(info.duration))
            fetched = download.download(
                url, directory, lambda _: None, format_selector=STYLE_FORMAT
            )
            _check_limits(fetched.path)
            return analyzer(fetched.path)
        finally:
            _clear(directory)


def _check_limits(path: Path) -> None:
    """Raise StyleFetchError if the video at path is over a limit (a direct
    link has no length or height to check before the download)."""
    try:
        media = probe_media(path)
    except FFmpegError as exc:
        raise StyleFetchError(f"cannot read the downloaded video: {exc}") from exc
    if media.duration > MAX_SECONDS:
        raise StyleFetchError(_too_long(media.duration))
    if media.height > MAX_HEIGHT:
        raise StyleFetchError(
            f"the video is {media.height}p; references are at most {MAX_HEIGHT}p"
        )


def _too_long(seconds: float) -> str:
    """Return the message of a video of the given length that is too long."""
    return (
        f"the video is {seconds / 60:.1f} min long; "
        f"references are at most {MAX_SECONDS // 60} min"
    )


def _clear(directory: Path) -> None:
    """Remove directory with everything in it; raises StyleFetchError if it
    is still there (the media must not stay on disk)."""
    shutil.rmtree(directory, ignore_errors=True)
    if directory.exists():
        logger.error("style reference media left in %s", directory)
        raise StyleFetchError(f"could not delete the reference media in {directory}")


@contextmanager
def _exclusive(reference_id: int) -> Iterator[None]:
    """Allow one fetch of a reference at a time (they share its directory)."""
    with _active_lock:
        if reference_id in _active:
            raise ReferenceBusy(f"reference {reference_id} is being analyzed")
        _active.add(reference_id)
    try:
        yield
    finally:
        with _active_lock:
            _active.discard(reference_id)
