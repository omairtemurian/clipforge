"""Shared helpers of the Pro Edit renderer tests (tests only): the clip that
the render tests cut from their 6 s 1280x720 30 fps sources, its base, the
sources and their lossless proxies (libx264 crf 0: frames outside an
effect decode to the very same pixels) and their frames."""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from clipforge.config import RenderSettings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import CutRange, EdlItem, FaceBox
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.proedit.render.base import ProEditBase
from clipforge.proedit.render.run import render_plan
from edl_fakes import plan
from frames import Pixels

CLIP = ClipSpan(7, 1.0, 5.0)
LOSSLESS = RenderSettings(encoder="libx264", crf=0)


def base_of(source: Path, cut_ranges: Sequence[CutRange] = ()) -> ProEditBase:
    """The base of CLIP of source, centered 9:16 (no faces), without
    cut_ranges."""
    faces: list[list[FaceBox]] = [[] for _ in sample_times(CLIP.start, CLIP.end)]
    crop = plan_crop(CLIP, "9:16", (1280, 720), faces, [])
    return ProEditBase(
        source, CLIP.start, CLIP.end, crop, "fill", cut_ranges=tuple(cut_ranges)
    )


def source_video(directory: Path, video_filter: str, still: bool) -> Path:
    """A 6 s 1280x720 30 fps h264/aac video of the lavfi video_filter (its
    first frame only if still) and a tone."""
    video = directory / "source.mp4"
    looped = (
        ["-loop", "1", "-framerate", "30", "-i"] if still else ["-f", "lavfi", "-i"]
    )
    picture = directory / "frame.png" if still else video_filter
    if still:
        run_ffmpeg(["-f", "lavfi", "-i", video_filter, "-frames:v", "1", picture])
    run_ffmpeg(
        [*looped, picture, "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video]
    )
    return video


def rendered(
    directory: Path, source: Path, items: list[EdlItem], name: str = "rendered"
) -> Path:
    """The lossless proxy of CLIP of source with items, as name.mp4."""
    output = directory / f"{name}.mp4"
    return render_plan(
        base_of(source), plan(items, "pro"), output, quality="proxy", settings=LOSSLESS
    )


def all_frames(video: Path, size: tuple[int, int] = (135, 240)) -> list[Pixels]:
    """Return every frame of video, scaled to size (RGB pixels)."""
    width, height = size
    args: list[str | Path] = ["-i", video, "-vf", f"scale={width}:{height}"]
    result = run_ffmpeg([*args, "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"])
    return list(np.frombuffer(result.stdout, np.uint8).reshape(-1, height, width, 3))
