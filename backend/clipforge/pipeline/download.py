"""Download of a URL source with yt-dlp, for the ingest step (SPEC 6.1)."""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from yt_dlp import YoutubeDL
from yt_dlp.utils import YoutubeDLError

from clipforge import config
from clipforge.pipeline.extractors import GENERIC, require_supported
from clipforge.pipeline.step import StepError
from clipforge.pipeline.ytdlp_session import failure_message, session_options

if TYPE_CHECKING:
    from yt_dlp import _YoutubeDLOptions

# The best video stream up to 1080p plus the best audio stream, or else the
# best single file up to 1080p (SPEC 6.1).
YTDLP_FORMAT = "bv*[height<=1080]+ba/b[height<=1080]"
# A direct link to a media file has no height to filter on (yt-dlp's generic
# extractor does not probe the file), so the 1080p limit would match nothing.
DIRECT_FORMAT = "bv*+ba/b"
# Formats are ranked H.264 video first (then by resolution) and AAC audio
# first, so the source needs no conversion; other codecs (AV1, VP9, Opus)
# are taken only when a page has no H.264/AAC (yt-dlp "Sorting Formats";
# checked with yt-dlp 2026.10.26 in tests/pipeline/test_ingest_formats.py).
FORMAT_SORT = ["vcodec:h264", "res", "acodec:m4a"]
DOWNLOAD_STEM = "download"

logger = logging.getLogger(__name__)

ProgressHook = Callable[[Mapping[str, Any]], object]


@dataclass(frozen=True)
class Download:
    """A downloaded video file and what yt-dlp reported about its page."""

    path: Path
    title: str | None
    channel: str | None
    channel_url: str | None


def is_url(source: str) -> bool:
    """Return True if source is an http(s) URL rather than a file path."""
    return urlsplit(source).scheme in ("http", "https")


def ytdlp_options(
    job_dir: Path, progress_hook: ProgressHook, format_selector: str = YTDLP_FORMAT
) -> "_YoutubeDLOptions":
    """Return the YoutubeDL params that download one video into job_dir.

    The file is saved as download.<ext>; separate video and audio streams are
    merged into an mp4. H.264/AAC formats are preferred (FORMAT_SORT). A
    playlist is not expanded (extract_flat), so it can be rejected before
    anything is downloaded. The cookies and JavaScript
    runtime of the settings are added (see session_options).
    """
    return {
        **session_options(config.settings),
        "format": format_selector,
        "format_sort": FORMAT_SORT,
        "merge_output_format": "mp4",
        "paths": {"home": str(job_dir)},
        "outtmpl": {"default": f"{DOWNLOAD_STEM}.%(ext)s"},
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "overwrites": True,
        "noprogress": True,
        "color": {"stdout": "never", "stderr": "never"},
        "logger": _YtDlpLogger(),
        "progress_hooks": [progress_hook],
    }


def download(
    url: str,
    job_dir: Path,
    on_progress: Callable[[float], None],
    format_selector: str | None = None,
) -> Download:
    """Download the video at url into job_dir (see ytdlp_options).

    format_selector replaces the 1080p selector of a page (Style Learning
    asks for 720p); a direct media link always uses DIRECT_FORMAT.

    on_progress receives the downloaded fraction of the current file, which
    never decreases (yt-dlp fetches the video and the audio one after the
    other). Raises UnsupportedSource (a StepError) if no installed yt-dlp
    extractor handles url, and StepError if url is a playlist or yt-dlp fails.
    """
    generic = require_supported(url) == GENERIC
    done = 0.0

    def hook(event: Mapping[str, Any]) -> None:
        nonlocal done
        total = event.get("total_bytes") or event.get("total_bytes_estimate")
        downloaded = event.get("downloaded_bytes")
        if total and downloaded is not None:
            done = max(done, min(downloaded / total, 1.0))
            on_progress(done)

    try:
        with YoutubeDL(
            ytdlp_options(
                job_dir,
                hook,
                DIRECT_FORMAT if generic else format_selector or YTDLP_FORMAT,
            )
        ) as ydl:
            info = ydl.extract_info(url, download=False)
            kind = dict(info).get("_type", "video")
            if kind != "video":
                raise StepError(f"{url} is a {kind}, not a single video")
            result: Mapping[str, Any] = ydl.process_ie_result(info, download=True)
    except YoutubeDLError as exc:
        raise StepError(failure_message("download failed", _clean(str(exc)))) from exc
    return Download(
        path=Path(result["requested_downloads"][0]["filepath"]),
        title=_text(result.get("title")),
        channel=_text(result.get("channel")) or _text(result.get("uploader")),
        channel_url=_text(result.get("channel_url"))
        or _text(result.get("uploader_url")),
    )


@dataclass(frozen=True)
class SourceInfo:
    """What a video page says about its video, read without downloading it."""

    title: str | None
    duration: float | None
    thumbnail_url: str | None


def probe(url: str) -> SourceInfo:
    """Read the title, duration and thumbnail URL of the video at url.

    Nothing is downloaded. Raises UnsupportedSource if no installed yt-dlp
    extractor handles url, and StepError if url is a playlist or a channel,
    or if yt-dlp cannot read the page (SIGN_IN_MESSAGE if the page needs a
    signed-in session).
    """
    require_supported(url)
    params: _YoutubeDLOptions = {
        **session_options(config.settings),
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "color": {"stdout": "never", "stderr": "never"},
        "logger": _YtDlpLogger(),
    }
    try:
        with YoutubeDL(params) as ydl:
            info: Mapping[str, Any] = ydl.extract_info(url, download=False)
    except YoutubeDLError as exc:
        message = failure_message("cannot read the video page", _clean(str(exc)))
        raise StepError(message) from exc
    kind = info.get("_type", "video")
    if kind != "video":
        raise StepError(f"{url} is a {kind}, not a single video")
    duration = info.get("duration")
    return SourceInfo(
        title=_text(info.get("title")),
        duration=float(duration)
        if isinstance(duration, int | float) and duration > 0
        else None,
        thumbnail_url=_text(info.get("thumbnail")),
    )


class _YtDlpLogger:
    """Sends yt-dlp's messages to this module's logger.

    yt-dlp passes its screen output to debug(); only lines that start with
    "[debug] " are debug messages.
    """

    def debug(self, message: str) -> None:
        level = logging.DEBUG if message.startswith("[debug] ") else logging.INFO
        logger.log(level, "%s", _clean(message))

    def info(self, message: str) -> None:
        logger.info("%s", _clean(message))

    def warning(
        self, message: str, *, once: bool = False, only_once: bool = False
    ) -> None:
        logger.warning("%s", _clean(message))

    def error(self, message: str) -> None:
        logger.error("%s", _clean(message))

    def stdout(self, message: str) -> None:
        logger.info("%s", _clean(message))

    def stderr(self, message: str) -> None:
        logger.error("%s", _clean(message))


def _clean(message: str) -> str:
    """Collapse whitespace (yt-dlp adds carriage returns) and drop "ERROR: "."""
    return " ".join(message.split()).removeprefix("ERROR: ")


def _text(value: object) -> str | None:
    """Return value if it is a non-empty string, else None."""
    return value if isinstance(value, str) and value else None
