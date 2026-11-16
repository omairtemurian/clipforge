"""A test video of flashes and beeps, and finding them in a render (tests
only): where a render puts parts of its source, by when they flash."""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from clipforge.ffmpeg import probe_media, run_ffmpeg

# The flashes video is black and silent but while this is 1: a white frame
# and a 1 kHz beep at 2, 5 and 8 s, for 0.25 s (frames 60-67, 150-157, ...).
FLASHES = "between(t,1.9999,2.24)+between(t,4.9999,5.24)+between(t,7.9999,8.24)"
SAMPLE_RATE = 48_000


def make_flashes(path: Path) -> Path:
    """Write a 12 s 640x360 30 fps h264/aac video with 48 kHz mono audio,
    black and silent but for the FLASHES, to path; return path."""
    white = f"drawbox=color=white:thickness=fill:enable='{FLASHES}'"
    beeps = f"aevalsrc='0.5*sin(2*PI*1000*t)*({FLASHES})':s={SAMPLE_RATE}:d=12"
    run_ffmpeg(
        ["-f", "lavfi", "-i", f"color=black:size=640x360:rate=30:duration=12,{white}"]
        + ["-f", "lavfi", "-i", beeps, "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        + ["-c:a", "aac", path]
    )
    return path


def onsets(times: Sequence[float]) -> list[float]:
    """Return the times of times that come more than 0.1 s after the one
    before them: when each run of them starts."""
    return [time for i, time in enumerate(times) if i == 0 or time - times[i - 1] > 0.1]


def flash_times(video: Path) -> list[float]:
    """Return the times of the frames of video that are mostly white."""
    gray = run_ffmpeg(
        ["-i", video, "-map", "0:v:0", "-vf", "scale=16:16,format=gray"]
        + ["-f", "rawvideo", "pipe:1"]
    ).stdout
    means = np.frombuffer(gray, np.uint8).reshape(-1, 256).mean(axis=1)
    fps = probe_media(video).fps
    return [index / fps for index in np.flatnonzero(means > 128)]


def beep_times(video: Path) -> list[float]:
    """Return the times of the samples of video's audio that are louder than
    a tenth of its loudest one."""
    pcm = run_ffmpeg(
        ["-i", video, "-map", "0:a:0", "-ac", "1", "-ar", str(SAMPLE_RATE)]
        + ["-f", "s16le", "pipe:1"]
    ).stdout
    levels = np.abs(np.frombuffer(pcm, np.int16).astype(np.int32))
    return [index / SAMPLE_RATE for index in np.flatnonzero(levels > levels.max() / 10)]
