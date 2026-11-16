"""Motion energy (SPEC-v2 3.2, clip anything): how much the picture of a
job's timeframe moves, per second -> motion.json.

ffmpeg decodes the timeframe at SAMPLE_FPS frames per second, scaled to
WIDTH x HEIGHT grey pixels (filters fps, scale, format; raw frames to
stdout). The energy of a pair of consecutive frames is the mean absolute
difference of their pixels over 255; a second's energy is the median of the
pairs whose later frame falls in it, so the one jump of a scene cut does not
count as motion. Stretches of high motion (motion_spans) are what the curate
prompt shows.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from clipforge.ffmpeg import FFmpegError, run_ffmpeg
from clipforge.models import MotionTrack
from clipforge.pipeline.step import StepError

SAMPLE_FPS = 4
WIDTH, HEIGHT = 64, 36
# Frames compared at a time, so a long video needs little memory.
CHUNK_FRAMES = 1024
DECIMALS = 4
# A second moves a lot when its energy is at least MOTION_FLOOR and
# MOTION_FACTOR times the timeframe's quiet level, its QUIET_PERCENTILE
# percentile: a talking head scores about 0.012, a busy synthetic test
# pattern 0.03 to 0.05. In a video that moves all the time only the bursts
# stand out.
MOTION_FLOOR = 0.02
MOTION_FACTOR = 1.5
QUIET_PERCENTILE = 25
# Spans of high motion this many seconds apart or less are joined.
MAX_GAP_S = 1


@dataclass(frozen=True, slots=True)
class MotionSpan:
    """A stretch of high motion from start to end source seconds; level is
    its mean energy over the highest energy of the timeframe (0..1)."""

    start: float
    end: float
    level: float


def read_frames(video: Path, start: float, end: float) -> npt.NDArray[np.uint8]:
    """Return the grey frames of [start, end) seconds of video, sampled at
    SAMPLE_FPS, as an array of shape (frames, HEIGHT * WIDTH).

    Raises StepError if ffmpeg cannot decode the video.
    """
    try:
        result = run_ffmpeg(
            [
                "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", video,
                "-map", "0:V:0", "-an",
                "-vf", f"fps={SAMPLE_FPS},scale={WIDTH}:{HEIGHT}:flags=area,"
                "format=gray",
                "-f", "rawvideo", "pipe:1",
            ]
        )  # fmt: skip
    except FFmpegError as exc:
        raise StepError(f"cannot measure the motion of {video}: {exc}") from exc
    size = WIDTH * HEIGHT
    usable = len(result.stdout) - len(result.stdout) % size
    return np.frombuffer(result.stdout[:usable], dtype=np.uint8).reshape(-1, size)


def frame_differences(frames: npt.NDArray[np.uint8]) -> npt.NDArray[np.float64]:
    """Return the energy of each pair of consecutive frames: the mean
    absolute difference of their pixels over 255; one fewer than frames."""
    parts = [np.zeros(0)]
    for first in range(0, len(frames) - 1, CHUNK_FRAMES):
        block = frames[first : first + CHUNK_FRAMES + 1].astype(np.int16)
        parts.append(np.abs(np.diff(block, axis=0)).mean(axis=1) / 255)
    return np.concatenate(parts)


def per_second(differences: Sequence[float], seconds: int) -> list[float]:
    """Return the energy of each of seconds seconds: the median of the
    differences whose later frame falls in it (frame k is at k / SAMPLE_FPS
    s), or 0 for a second without any."""
    buckets: list[list[float]] = [[] for _ in range(seconds)]
    for index, value in enumerate(differences, start=1):
        second = index // SAMPLE_FPS
        if second < seconds:
            buckets[second].append(float(value))
    return [round(float(np.median(b)), DECIMALS) if b else 0.0 for b in buckets]


def measure_motion(video: Path, start: float, end: float) -> MotionTrack:
    """Return the motion energy of each second of [start, end) seconds of
    video. Raises StepError if the video cannot be decoded."""
    frames = read_frames(video, start, end)
    seconds = math.ceil(round(end - start, 3))
    return MotionTrack(
        start=start, scores=per_second(frame_differences(frames).tolist(), seconds)
    )


def motion_spans(track: MotionTrack) -> list[MotionSpan]:
    """Return the stretches of high motion of track, in order.

    A second moves a lot when its energy is at least MOTION_FLOOR and
    MOTION_FACTOR times the QUIET_PERCENTILE percentile of the track; runs
    of such seconds no more than MAX_GAP_S apart make one span.
    """
    scores = track.scores
    if not scores:
        return []
    peak = max(scores)
    quiet = float(np.percentile(scores, QUIET_PERCENTILE))
    threshold = max(MOTION_FLOOR, MOTION_FACTOR * quiet)
    active = [index for index, score in enumerate(scores) if score >= threshold]
    runs: list[list[int]] = []
    for index in active:
        if runs and index - runs[-1][-1] <= MAX_GAP_S + 1:
            runs[-1].append(index)
        else:
            runs.append([index])
    spans = []
    for run in runs:
        level = float(np.mean([scores[i] for i in range(run[0], run[-1] + 1)]))
        spans.append(
            MotionSpan(
                round(track.start + run[0], 3),
                round(track.start + run[-1] + 1, 3),
                round(level / peak, 2),
            )
        )
    return spans
