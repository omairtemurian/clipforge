"""Measuring a video's edit features in one pass (SPEC-v3 4.3, 2.1).

ffmpeg decodes the span at the video's frame rate (rounded), scaled to
ANALYSIS_WIDTH pixels wide (frame_stream.stream_frames); each frame gives
its color (features/color), its cut descriptor (features/cuts) and, with
the frame before it, its motion (features/motion). Flashes are found first,
so cuts skip them and no motion is measured into or out of a flash or
across a cut. Every time is in seconds from the start of the span.
"""

import math
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel, Field

from clipforge.ffmpeg import FFmpegError, probe_media
from clipforge.pipeline.frame_stream import stream_frames
from clipforge.pipeline.step import StepError
from clipforge.proedit.features.color import (
    ColorStats,
    Frame,
    FrameColor,
    color_stats,
    frame_color,
)
from clipforge.proedit.features.cuts import (
    CutStats,
    Descriptor,
    cut_stats,
    detect_cuts,
    frame_descriptor,
)
from clipforge.proedit.features.flashes import FlashStats, detect_flashes
from clipforge.proedit.features.motion import (
    Grey,
    MotionStats,
    PairMotion,
    motion_stats,
    pair_motion,
)

ANALYSIS_WIDTH = 320


class VideoFeatures(BaseModel):
    """The edit features of a stretch of video: its length (seconds), the
    frame rate it was measured at, cuts, motion, color and flashes."""

    duration: float = Field(ge=0)
    fps: int = Field(gt=0)
    cuts: CutStats
    motion: MotionStats
    color: ColorStats
    flashes: FlashStats


def measure_video(
    path: Path,
    *,
    start: float = 0.0,
    end: float | None = None,
    width: int = ANALYSIS_WIDTH,
    on_frame: Callable[[Frame, Grey], None] | None = None,
) -> VideoFeatures:
    """Return the edit features of [start, end) seconds of path (to its end
    without end); on_frame, if given, also gets each sampled RGB frame and
    its grey version, in order. Raises StepError if the video cannot be
    read."""
    try:
        info = probe_media(path)
        fps = max(1, round(info.fps))
        stop = info.duration if end is None else min(end, info.duration)
        count = max(0, math.floor((stop - start) * fps + 1e-6))
        height = max(2, round(width * info.height / info.width / 2) * 2)
        colors: list[FrameColor] = []
        descriptors: list[Descriptor] = []
        greys: list[Grey] = []
        pairs: list[PairMotion | None] = []
        for rgb in stream_frames(path, start, count, (width, height), fps):
            colors.append(frame_color(rgb))
            descriptors.append(frame_descriptor(rgb))
            grey = np.asarray(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), dtype=np.uint8)
            pairs.append(pair_motion(greys[-1], grey) if greys else None)
            greys = [grey]
            if on_frame is not None:
                on_frame(rgb, grey)
    except FFmpegError as exc:
        raise StepError(f"cannot measure the features of {path}: {exc}") from exc
    return features_of(colors, descriptors, pairs, fps)


def features_of(
    colors: list[FrameColor],
    descriptors: list[Descriptor],
    pairs: list[PairMotion | None],
    fps: int,
) -> VideoFeatures:
    """Return the features of frames whose color, cut descriptor and motion
    from the frame before are colors[k], descriptors[k] and pairs[k]."""
    flashes = detect_flashes(colors, fps)
    flash = [False] * len(colors)
    for event in flashes.flashes:
        for index in range(round(event.start * fps), round(event.end * fps)):
            flash[index] = True
    cut_frames = detect_cuts(descriptors, flash)
    cuts = set(cut_frames)
    steady = [
        None if k in cuts or flash[k] or (k > 0 and flash[k - 1]) else pair
        for k, pair in enumerate(pairs)
    ]
    return VideoFeatures(
        duration=round(len(colors) / fps, 4),
        fps=fps,
        cuts=cut_stats(cut_frames, len(colors), fps),
        motion=motion_stats(steady, fps),
        color=color_stats(colors, fps),
        flashes=flashes,
    )
