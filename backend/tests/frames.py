"""Reading the frames of rendered videos in tests (tests only)."""

from collections.abc import Iterable
from pathlib import Path

import numpy as np
import numpy.typing as npt
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.pipeline.render_graph import subtitles_filter

Pixels = npt.NDArray[np.uint8]


def frame_at(video: Path, time_s: float) -> Pixels:
    """Return the RGB pixels (height, width, 3) of the frame of video at time_s."""
    info = probe_media(video)
    result = run_ffmpeg(
        ["-ss", f"{time_s:.3f}", "-i", video, "-frames:v", "1"]
        + ["-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    )
    pixels = np.frombuffer(result.stdout, np.uint8)
    return pixels.reshape(info.height, info.width, 3)


def caption_frame(
    ass: Path, size: tuple[int, int], time_s: float, fps: int = 100
) -> Pixels:
    """Return the RGB pixels of the frame at time_s of the captions in the
    ASS file ass, drawn by libass on a black frame of size (width, height)
    at fps frames a second (100: a frame every 10 ms)."""
    width, height = size
    result = run_ffmpeg(
        ["-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}:d=3"]
        + ["-vf", subtitles_filter(ass), "-ss", f"{time_s:.3f}", "-frames:v", "1"]
        + ["-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    )
    return np.frombuffer(result.stdout, np.uint8).reshape(height, width, 3)


def drawn_extent(pixels: Pixels, threshold: int = 40) -> tuple[int, int]:
    """Return the (width, height) in pixels of the box around every pixel
    brighter than threshold in any channel; (0, 0) if there is none."""
    mask = pixels.max(axis=2) > threshold
    rows, cols = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))
    if rows.size == 0:
        return 0, 0
    return int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1)


def png_pixels(png: Path, size: tuple[int, int]) -> Pixels:
    """Return the RGB pixels of the image png, which is size (width, height)."""
    width, height = size
    result = run_ffmpeg(
        ["-i", png, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    )
    return np.frombuffer(result.stdout, np.uint8).reshape(height, width, 3)


def numbered_frames(video: Path, numbers: Iterable[int]) -> dict[int, Pixels]:
    """Return the RGB pixels of the frames numbers (0 is the first) of video,
    decoded from its start, so each is exactly that frame (frame_at seeks
    and lands on the first frame at or after a time)."""
    info = probe_media(video)
    wanted = sorted(set(numbers))
    picks = "+".join(f"eq(n,{n})" for n in wanted)
    result = run_ffmpeg(
        ["-i", video, "-vf", f"select='{picks}'", "-fps_mode", "passthrough"]
        + ["-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    )
    pixels = np.frombuffer(result.stdout, np.uint8)
    frames = pixels.reshape(-1, info.height, info.width, 3)
    return dict(zip(wanted, frames, strict=True))


def frame_hashes(video: Path) -> list[str]:
    """Return the SHA-256 of each decoded frame of video's first video
    stream, in order (ffmpeg's framehash muxer)."""
    result = run_ffmpeg(
        ["-i", video, "-map", "0:v:0", "-f", "framehash", "-hash", "sha256", "-"]
    )
    lines = result.stdout.decode().splitlines()
    return [line.rsplit(",", 1)[-1].strip() for line in lines if line[:1] != "#"]
