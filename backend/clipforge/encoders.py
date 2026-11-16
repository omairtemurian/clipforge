"""The H.264 encoders a render can use, and their ffmpeg options.

libx264 is the software encoder (settings.preset and settings.crf).
h264_videotoolbox is Apple's hardware encoder: it has no -crf or -preset, so
its quality is -q:v (1-100, higher is better), mapped from the crf
(video_quality; verified with `ffmpeg -h encoder=h264_videotoolbox` and SSIM,
docs/decisions.md). The default is h264_videotoolbox when the ffmpeg build
lists it (`ffmpeg -hide_banner -encoders`), else libx264.
"""

import functools
import logging
import subprocess
from typing import Literal, get_args

logger = logging.getLogger(__name__)

VideoEncoder = Literal["libx264", "h264_videotoolbox"]
VIDEO_ENCODERS: tuple[VideoEncoder, ...] = get_args(VideoEncoder)
SOFTWARE: VideoEncoder = "libx264"
HARDWARE: VideoEncoder = "h264_videotoolbox"
LIST_TIMEOUT_S = 30.0


@functools.cache
def available_encoders(ffmpeg: str) -> tuple[VideoEncoder, ...]:
    """Return the VIDEO_ENCODERS that the ffmpeg binary lists, in order.

    Asks `ffmpeg -hide_banner -encoders` once per binary. libx264 is always
    included: an ffmpeg that cannot be run fails later, with its own error.
    """
    try:
        listing = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=LIST_TIMEOUT_S,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("cannot list the encoders of %s: %s", ffmpeg, exc)
        listing = ""
    names = {line.split()[1] for line in listing.splitlines() if len(line.split()) > 1}
    return tuple(e for e in VIDEO_ENCODERS if e == SOFTWARE or e in names)


def default_encoder(ffmpeg: str) -> VideoEncoder:
    """Return h264_videotoolbox if ffmpeg has it, else libx264."""
    return HARDWARE if HARDWARE in available_encoders(ffmpeg) else SOFTWARE


def video_quality(crf: int) -> int:
    """Return the h264_videotoolbox -q:v for a libx264 crf: 120 - 2.5 * crf,
    within 1-100 (crf 20 -> 70, crf 28 -> 50)."""
    return max(1, min(100, round(120 - 2.5 * crf)))


def encoder_args(encoder: VideoEncoder, preset: str, crf: int) -> list[str]:
    """Return the ffmpeg output options that encode the video with encoder
    at the quality of crf (and, for libx264, preset)."""
    if encoder == HARDWARE:
        return ["-c:v", HARDWARE, "-q:v", str(video_quality(crf))]
    return ["-c:v", SOFTWARE, "-preset", preset, "-crf", str(crf)]
