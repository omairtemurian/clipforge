"""Typed wrappers around the ffmpeg and ffprobe command-line tools.

Commands are argument lists handed straight to subprocess, never shell
strings. Path arguments are passed as absolute paths, so a file name can never
be read as an option ("-x.mp4") or a protocol ("http:x.mp4"); text inside a
filter graph, such as a file name in a filter's options, is escaped with
filter_value. Every failure raises FFmpegError, whose message ends with the
tail of the tool's stderr: ffmpeg's own explanation of what went wrong.
"""

import json
import logging
import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from clipforge import config
from clipforge.ffmpeg_args import spilled_args

logger = logging.getLogger(__name__)

LIBASS_FILTER = "subtitles"
LIBASS_MISSING = (
    "ffmpeg lacks libass (subtitles filter); install with: brew install ffmpeg-full"
)
WAV_SAMPLE_RATE = 16_000
# mjpeg quality scale for -q:v: 2 (best) to 31 (worst).
JPEG_QUALITY = 2
STDERR_TAIL_LINES = 20
STDERR_TAIL_CHARS = 2_000
# The characters a backslash escapes in a filter's option value and in a
# filter graph (filter_value), with the whitespace that both levels strip
# from the ends of a value.
WHITESPACE = " \t\n\r"
OPTION_SPECIAL = "\\':" + WHITESPACE
GRAPH_SPECIAL = "\\'[],;" + WHITESPACE

LogLevel = Literal[
    "quiet", "panic", "fatal", "error", "warning", "info", "verbose", "debug", "trace"
]
Arg = str | Path


class FFmpegError(RuntimeError):
    """An ffmpeg/ffprobe command failed, or it described unusable media.

    `command` is the argument list that ran (empty when the error comes from
    checking ffprobe's report) and `stderr_tail` holds the last lines the tool
    wrote to stderr; the message ends with that tail.
    """

    def __init__(
        self, message: str, *, command: Sequence[str] = (), stderr: str = ""
    ) -> None:
        self.command = list(command)
        self.stderr_tail = _tail(stderr)
        super().__init__(
            f"{message}: {self.stderr_tail}" if self.stderr_tail else message
        )


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """What ffprobe reports about a video file.

    width and height are the displayed frame size: rotation metadata is
    applied, as it is to the frames ffmpeg decodes. fps is the average frame
    rate. The audio fields describe the first audio stream and are None when
    there is none; title is the container's title tag, if set.
    """

    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    pix_fmt: str
    audio_codec: str | None
    sample_rate: int | None
    channels: int | None
    title: str | None


def ffmpeg_bin() -> str:
    """Return the ffmpeg binary to run: the ffmpeg_bin setting, which defaults
    to ffmpeg-full's if installed, else `ffmpeg` on PATH."""
    return config.settings.ffmpeg_bin


def ffprobe_bin() -> str:
    """Return the ffprobe binary to run (see ffmpeg_bin)."""
    return config.settings.ffprobe_bin


def check_ffmpeg() -> None:
    """Raise FFmpegError unless the configured ffmpeg has the subtitles
    filter, which needs libass and which captions are burned in with.

    Also raises FFmpegError if ffmpeg cannot be run.
    """
    result = _run([ffmpeg_bin(), "-hide_banner", "-filters"])
    filters = result.stdout.decode("utf-8", errors="replace").splitlines()
    if not any(
        len(parts := line.split()) > 1 and parts[1] == LIBASS_FILTER for line in filters
    ):
        raise FFmpegError(LIBASS_MISSING, command=[ffmpeg_bin(), "-filters"])


def run_ffmpeg(
    args: Sequence[Arg], *, loglevel: LogLevel = "error"
) -> subprocess.CompletedProcess[bytes]:
    """Run `ffmpeg <args>` and return the finished process.

    ffmpeg never reads stdin, overwrites existing outputs (-y) and prints no
    banner or progress lines; stdout and stderr are captured as bytes. At the
    default loglevel stderr holds only errors; pass "info" to read the reports
    that filters such as loudnorm print. Long filter graphs are read from a
    file (ffmpeg_args.spilled_args). Raises FFmpegError if ffmpeg is
    missing or exits with a non-zero status.
    """
    base = [ffmpeg_bin(), "-nostdin", "-hide_banner", "-nostats", "-loglevel", loglevel]
    with spilled_args([_arg(arg) for arg in args]) as spilled:
        return _run([*base, "-y", *spilled])


def filter_value(text: str) -> str:
    """Return text escaped as the value of a filter option in a filter graph
    (-vf or -filter_complex), which ffmpeg reads back as exactly text.

    ffmpeg unescapes a graph at two levels (ffmpeg-filters, "Notes on
    filtergraph escaping"): the graph, where \\ ' [ ] , ; are special, then
    each filter's options, where \\ ' : are. A backslash makes the next
    character literal at either level, so text is escaped for the options
    and the result again for the graph. Whitespace is escaped too, as both
    levels strip it from the ends of a value.
    """
    return _escape(_escape(text, OPTION_SPECIAL), GRAPH_SPECIAL)


def ffprobe_json(path: Path) -> dict[str, Any]:
    """Return ffprobe's report on a media file: its "format" and "streams".

    Raises FFmpegError if ffprobe cannot open or parse the file.
    """
    result = _run(
        [
            ffprobe_bin(), "-hide_banner", "-loglevel", "error",
            "-show_format", "-show_streams", "-of", "json", _arg(path),
        ]
    )  # fmt: skip
    report: dict[str, Any] = json.loads(result.stdout)
    return report


def probe_media(path: Path) -> MediaInfo:
    """Describe the video file at path (see MediaInfo).

    Raises FFmpegError if ffprobe cannot read the file, if it has no video
    stream (cover art in an audio file does not count), or if its duration or
    frame rate is unknown (a still image has no duration).
    """
    report = ffprobe_json(path)
    fmt: dict[str, Any] = report.get("format", {})
    streams: list[dict[str, Any]] = report.get("streams", [])
    video = next((stream for stream in streams if _is_video(stream)), None)
    if video is None:
        raise FFmpegError(f"no video stream in {path}")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    width, height = int(video["width"]), int(video["height"])
    if _rotation(video) % 180 == 90:
        width, height = height, width
    return MediaInfo(
        duration=_duration(path, fmt, video),
        width=width,
        height=height,
        fps=_frame_rate(path, video),
        video_codec=str(video.get("codec_name", "unknown")),
        pix_fmt=str(video.get("pix_fmt", "unknown")),
        audio_codec=None if audio is None else str(audio.get("codec_name", "unknown")),
        sample_rate=None if audio is None else int(audio["sample_rate"]),
        channels=None if audio is None else int(audio["channels"]),
        title=fmt.get("tags", {}).get("title") or None,
    )


def extract_frame(src: Path, dst: Path, time_s: float) -> Path:
    """Save the first frame of src at or after time_s seconds as an image.

    The image format follows dst's suffix (.jpg, .png, ...); JPEGs use the
    best mjpeg quality. Returns dst. Raises ValueError for a negative time and
    FFmpegError if src has no frame at that time (e.g. past its end).
    """
    if time_s < 0:
        raise ValueError(f"frame time must be >= 0 s, got {time_s}")
    run_ffmpeg(
        [
            "-ss", f"{time_s:.6f}", "-i", src,
            "-frames:v", "1", "-update", "1", "-q:v", str(JPEG_QUALITY), dst,
        ]
    )  # fmt: skip
    return dst


def extract_audio_wav(
    src: Path, dst: Path, *, start: float = 0.0, duration: float | None = None
) -> Path:
    """Decode the first audio stream of src to a 16 kHz mono 16-bit PCM WAV.

    This is the audio format that transcription and audio analysis read; other
    channel layouts are downmixed to mono. With start and duration, only the
    audio from start seconds on, for at most duration seconds, is written
    (`-ss` before the input, `-t` after it); cutting a PCM WAV this way is
    exact to the sample. Returns dst. Raises ValueError for a negative start
    or a duration that is not positive, and FFmpegError if src has no audio
    stream or cannot be decoded.
    """
    if start < 0:
        raise ValueError(f"audio start must be >= 0 s, got {start}")
    if duration is not None and duration <= 0:
        raise ValueError(f"audio duration must be > 0 s, got {duration}")
    seek = ["-ss", f"{start:.6f}"] if start else []
    limit = [] if duration is None else ["-t", f"{duration:.6f}"]
    run_ffmpeg(
        [
            *seek, "-i", src, *limit, "-map", "0:a:0", "-ac", "1",
            "-ar", str(WAV_SAMPLE_RATE), "-c:a", "pcm_s16le", "-f", "wav", dst,
        ]
    )  # fmt: skip
    return dst


def _run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run a command, raising FFmpegError if it is missing or exits non-zero."""
    logger.debug("running %s", shlex.join(command))
    try:
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, capture_output=True, check=False
        )
    except FileNotFoundError as exc:
        raise FFmpegError(
            f"{command[0]} not found; install ffmpeg with libass "
            "(`brew install ffmpeg-full`) or set ffmpeg_bin/ffprobe_bin",
            command=command,
        ) from exc
    if result.returncode != 0:
        raise FFmpegError(
            f"{command[0]} exited with status {result.returncode}",
            command=command,
            stderr=result.stderr.decode("utf-8", errors="replace"),
        )
    return result


def _arg(value: Arg) -> str:
    """Return a command-line argument, making a Path absolute."""
    return str(value.absolute()) if isinstance(value, Path) else value


def _escape(text: str, special: str) -> str:
    """Return text with a backslash before each of its characters in special."""
    return "".join(f"\\{char}" if char in special else char for char in text)


def _tail(text: str) -> str:
    """Return the last STDERR_TAIL_LINES lines of text, capped at
    STDERR_TAIL_CHARS characters."""
    lines = text.strip().splitlines()[-STDERR_TAIL_LINES:]
    return "\n".join(line.rstrip() for line in lines)[-STDERR_TAIL_CHARS:]


def _is_video(stream: dict[str, Any]) -> bool:
    """True for a video stream that is not an attached picture (cover art)."""
    cover_art = stream.get("disposition", {}).get("attached_pic", 0)
    return stream.get("codec_type") == "video" and not cover_art


def _rotation(stream: dict[str, Any]) -> int:
    """Return the stream's display rotation in degrees (0 when unrotated)."""
    for side_data in stream.get("side_data_list", []):
        if "rotation" in side_data:
            return round(float(side_data["rotation"]))
    return 0


def _duration(path: Path, fmt: dict[str, Any], video: dict[str, Any]) -> float:
    """Return the container's duration, else the video stream's, in seconds."""
    for section in (fmt, video):
        try:
            seconds = float(section["duration"])
        except (KeyError, ValueError):
            continue
        if seconds > 0:
            return seconds
    raise FFmpegError(f"unknown duration for {path}")


def _frame_rate(path: Path, video: dict[str, Any]) -> float:
    """Return the average frame rate, else the stream's base frame rate."""
    for key in ("avg_frame_rate", "r_frame_rate"):
        num, _, den = str(video.get(key, "")).partition("/")
        if num.isdigit() and den.isdigit() and int(num) > 0 and int(den) > 0:
            return int(num) / int(den)
    raise FFmpegError(f"unknown frame rate for {path}")
