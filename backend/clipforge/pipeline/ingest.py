"""Ingest step (SPEC 6.1): turn a project's source into the files later steps use.

It writes into the job directory:
- source.mp4: the video with h264 video and aac audio,
- audio.wav: 16 kHz mono 16-bit PCM of the whole video,
- thumb.jpg: the frame at 10% of the duration,
- meta.json: a SourceMeta, written last, so that it marks a finished ingest.
"""

import logging
from pathlib import Path

from clipforge.ffmpeg import extract_audio_wav, extract_frame, probe_media
from clipforge.models import ProcessingSettings, SourceMeta
from clipforge.pipeline.download import Download, download, is_url
from clipforge.pipeline.step import (
    AUDIO,
    META,
    SOURCE,
    THUMB,
    StepError,
    StepSettings,
    is_done,
    write_json,
)
from clipforge.pipeline.transcode import write_source
from clipforge.sources import dropbox, gdrive

THUMB_AT = 0.1
# The step's progress when each stage ends. A conversion (pipeline/transcode)
# reports CONVERT_START when it starts, then rises to SOURCE_READY; the
# processing view shows its "Converting video" sub-step in that band
# (frontend lib/processingSteps.ts INGEST_CONVERT_BAND).
DOWNLOADED, CONVERT_START, SOURCE_READY = 0.5, 0.51, 0.9
AUDIO_READY, THUMB_READY = 0.95, 0.98

logger = logging.getLogger(__name__)


def run(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
    """Ingest settings.source into job_dir and return the path of meta.json.

    A URL is downloaded with yt-dlp and a local file is copied; either one is
    converted if it is not an h264/aac mp4 (pipeline/transcode.write_source).
    Skips the work if meta.json exists, unless force. Raises StepError if the
    source file is missing, the download fails, the video has no audio or the
    project's timeframe starts after the video ends, and FFmpegError if
    ffmpeg fails.
    """
    meta_path = job_dir / META
    if is_done(meta_path, force=force):
        logger.info("%s exists; skipping ingest", meta_path)
        settings.report_progress(1.0)
        return meta_path
    job_dir.mkdir(parents=True, exist_ok=True)
    meta_path.unlink(missing_ok=True)

    source = job_dir / SOURCE
    fetched = _acquire(settings, source)
    settings.report_progress(SOURCE_READY)
    info = probe_media(source)
    start, end = _timeframe(settings.processing, info.duration)
    extract_audio_wav(source, job_dir / AUDIO)
    settings.report_progress(AUDIO_READY)
    extract_frame(source, job_dir / THUMB, THUMB_AT * info.duration)
    settings.report_progress(THUMB_READY)

    title = fetched.title if fetched else None
    meta = SourceMeta(
        title=title or info.title or Path(settings.source).stem,
        duration=info.duration,
        width=info.width,
        height=info.height,
        fps=info.fps,
        timeframe_start=start,
        timeframe_end=end,
        channel=fetched.channel if fetched else None,
        channel_url=fetched.channel_url if fetched else None,
    )
    write_json(meta_path, meta)
    settings.report_progress(1.0)
    logger.info("ingested %r (%.1fs) into %s", meta.title, meta.duration, job_dir)
    return meta_path


def _acquire(settings: StepSettings, source: Path) -> Download | None:
    """Write settings.source to the path source (transcode.write_source, with
    the video_encoder of the settings and its progress in the
    CONVERT_START..SOURCE_READY band).

    A URL is downloaded first (_download), and what it reported is returned; a local
    file returns None. Raises StepError if the local file does not exist.
    """

    def on_progress(done: float) -> None:
        settings.report_progress(CONVERT_START + done * (SOURCE_READY - CONVERT_START))

    encoder = settings.cfg.video_encoder
    if is_url(settings.source):
        fetched = _download(settings.source, source.parent, settings)
        write_source(
            fetched.path, source, move=True, encoder=encoder, on_progress=on_progress
        )
        return fetched
    local = Path(settings.source)
    if not local.is_file():
        raise StepError(f"source file not found: {local}")
    write_source(local, source, move=False, encoder=encoder, on_progress=on_progress)
    return None


def _download(url: str, job_dir: Path, settings: StepSettings) -> Download:
    """Download url into job_dir: a Google Drive or Dropbox file link with
    that service's API while its account is connected (sources.gdrive,
    sources.dropbox), anything else (and those links without a connection)
    with yt-dlp."""

    def on_progress(done: float) -> None:
        settings.report_progress(done * DOWNLOADED)

    drive_id = gdrive.drive_file_id(url)
    if drive_id is not None and gdrive.is_connected():
        return gdrive.download(drive_id, job_dir, on_progress)
    dropbox_url = dropbox.dropbox_link(url)
    if dropbox_url is not None and dropbox.is_connected():
        return dropbox.download(dropbox_url, job_dir, on_progress)
    return download(url, job_dir, on_progress)


def _timeframe(processing: ProcessingSettings, duration: float) -> tuple[float, float]:
    """Return the [start, end] seconds of the video that later steps consider.

    Without a timeframe that is the whole video; an end after the end of the
    video is clamped to it. Raises StepError if the start is not before the
    end of the video.
    """
    start = processing.timeframe_start or 0.0
    if start >= duration:
        raise StepError(
            f"the timeframe starts at {start:g}s but the video is only "
            f"{duration:g}s long"
        )
    end = duration if processing.timeframe_end is None else processing.timeframe_end
    if end > duration:
        logger.info(
            "timeframe end %gs is after the video end; using %gs", end, duration
        )
        end = duration
    return start, end
