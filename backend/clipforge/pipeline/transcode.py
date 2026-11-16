"""Writing an ingested video as the h264/aac mp4 that later steps and browsers
read (SPEC 6.1), converting only the streams that need it.

The video is encoded with the configured encoder (Settings.video_encoder,
as for renders: h264_videotoolbox when ffmpeg has it); if that encoder
fails, libx264 encodes it instead. A conversion reports its progress (ffmpeg
-progress) and logs it as "Converting video to H.264: 42%".
"""

import logging
import os
import shutil
from collections.abc import Callable
from pathlib import Path

from clipforge.encoders import SOFTWARE, VideoEncoder, encoder_args
from clipforge.ffmpeg import FFmpegError, ffprobe_json, probe_media
from clipforge.ffmpeg_progress import run_ffmpeg_progress
from clipforge.pipeline.step import StepError

# Streams in these formats play in browsers, so they are copied unchanged.
COPY_VIDEO_CODEC = "h264"
COPY_PIX_FMTS = ("yuv420p", "yuvj420p")
COPY_AUDIO_CODEC = "aac"
# ffprobe names the demuxer of every MP4-family file "mov,mp4,m4a,3gp,3g2,mj2".
MP4_FORMAT = "mp4"
# H.264 4:2:0 needs an even width and height.
EVEN_SIZE = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
# The quality of a converted source: libx264 crf 18 (preset medium), or the
# h264_videotoolbox -q:v that encoders.video_quality maps it to.
CRF = 18
PRESET = "medium"
ENCODE_AUDIO = ("-c:a", "aac")
VIDEO_LABEL = "Converting video to H.264"
AUDIO_LABEL = "Converting audio to AAC"

logger = logging.getLogger(__name__)

Progress = Callable[[float], None]


def write_source(
    src: Path,
    dst: Path,
    *,
    move: bool,
    encoder: VideoEncoder = SOFTWARE,
    on_progress: Progress | None = None,
) -> None:
    """Write the video src to dst as an mp4 with h264 video and aac audio.

    Streams that already are h264 (8-bit 4:2:0) or aac are copied; others are
    encoded (video with encoder, falling back to libx264; audio as aac). An
    mp4 that needs no change is copied byte for byte. on_progress, if set,
    receives the converted share (0 to 1) during a conversion only. With
    move, src is moved instead of copied, or deleted after a conversion.
    Raises StepError if src has no audio stream and FFmpegError if ffmpeg
    fails.
    """
    info = probe_media(src)
    if info.audio_codec is None:
        raise StepError(f"{src.name} has no audio track; ClipForge needs its speech")
    copy_video = info.video_codec == COPY_VIDEO_CODEC and info.pix_fmt in COPY_PIX_FMTS
    copy_audio = info.audio_codec == COPY_AUDIO_CODEC
    in_mp4 = MP4_FORMAT in str(ffprobe_json(src)["format"]["format_name"]).split(",")
    unchanged = copy_video and copy_audio and in_mp4
    if unchanged and move:
        logger.info("moving %s (an h264/aac mp4) to %s", src.name, dst.name)
        os.replace(src, dst)
        return

    tmp = dst.with_suffix(".tmp.mp4")
    try:
        if unchanged:
            logger.info("copying %s (an h264/aac mp4) to %s", src.name, dst.name)
            shutil.copyfile(src, tmp)
        else:
            logger.info(
                "converting %s to %s: video %s, audio %s",
                src.name,
                dst.name,
                "copied" if copy_video else f"{info.video_codec} -> h264",
                "copied" if copy_audio else f"{info.audio_codec} -> aac",
            )
            if copy_video:
                report = _reporter(AUDIO_LABEL, on_progress)
                _convert(src, tmp, None, copy_audio, info.duration, report)
            else:
                _convert_video(
                    src, tmp, encoder, copy_audio, info.duration, on_progress
                )
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
    if move:
        src.unlink()


def _convert_video(
    src: Path,
    tmp: Path,
    encoder: VideoEncoder,
    copy_audio: bool,
    duration: float,
    on_progress: Progress | None,
) -> None:
    """Convert src into tmp, encoding the video with encoder, or with libx264
    (its progress starting again from 0) if encoder, a hardware one, fails."""
    try:
        _convert(
            src, tmp, encoder, copy_audio, duration, _reporter(VIDEO_LABEL, on_progress)
        )
    except FFmpegError as exc:
        if encoder == SOFTWARE:
            raise
        logger.warning("%s failed (%s); converting with %s", encoder, exc, SOFTWARE)
        _convert(
            src,
            tmp,
            SOFTWARE,
            copy_audio,
            duration,
            _reporter(VIDEO_LABEL, on_progress),
        )


def _convert(
    src: Path,
    tmp: Path,
    encoder: VideoEncoder | None,
    copy_audio: bool,
    duration: float,
    report: Progress,
) -> None:
    """Write src's first video and audio streams into the mp4 tmp: the video
    copied (encoder None) or encoded with encoder, the audio copied or aac."""
    # 0:V skips cover art, which ffmpeg also counts as a video stream.
    maps = ("-map", "0:V:0", "-map", "0:a:0")
    video = (
        ["-c:v", "copy"]
        if encoder is None
        else [
            "-vf",
            EVEN_SIZE,
            *encoder_args(encoder, PRESET, CRF),
            "-pix_fmt",
            "yuv420p",
        ]
    )
    audio = ("-c:a", "copy") if copy_audio else ENCODE_AUDIO
    faststart = ("-movflags", "+faststart")
    report(0.0)
    run_ffmpeg_progress(
        ["-i", src, *maps, *video, *audio, *faststart, tmp], duration, report
    )


def _reporter(label: str, on_progress: Progress | None) -> Progress:
    """Return a progress callback that passes the share on to on_progress
    and logs "<label>: N%" each time the whole percent rises."""
    logged = -1

    def report(fraction: float) -> None:
        nonlocal logged
        percent = int(fraction * 100)
        if percent > logged:
            logged = percent
            logger.info("%s: %d%%", label, percent)
        if on_progress is not None:
            on_progress(fraction)

    return report
