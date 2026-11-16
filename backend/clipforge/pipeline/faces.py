"""The faces in frames of a video, sampled 10 times a second (SPEC 6.8).

ffmpeg decodes the frames (find_faces: in one run per clip, pipeline/
frame_stream; decode_frames: in slices of SLICE_SAMPLES), scaled down so
their longer side is at most ANALYSIS_SIZE pixels (the face model sees 192x192
anyway), and the MediaPipe models of pipeline/detectors find the faces (or
people) in each one. Boxes are given in source pixels.
"""

import math
from collections.abc import Callable
from pathlib import Path

import numpy as np
import numpy.typing as npt

from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import FaceBox
from clipforge.pipeline.detectors import DetectFaces, Frame, face_detector
from clipforge.pipeline.face_cache import FaceCache
from clipforge.pipeline.frame_stream import stream_frames

__all__ = [
    "DetectFaces",
    "Frame",
    "analysis_size",
    "decode_frames",
    "face_detector",
    "find_faces",
    "sample_times",
]

# Frames sampled per second of a clip (TASK-22 tracker quality; SPEC 6.8 had 5).
SAMPLE_FPS = 10
# Frames one ffmpeg run decodes: 5 s, 35 MB of 640x360 RGB.
SLICE_SAMPLES = 50
ANALYSIS_SIZE = 640


def sample_times(start: float, end: float) -> list[float]:
    """Return the times of the frames sampled from [start, end) seconds:
    start, then every 1 / SAMPLE_FPS seconds, rounded to milliseconds."""
    count = max(1, math.ceil(round((end - start) * SAMPLE_FPS, 6)))
    return [round(start + k / SAMPLE_FPS, 3) for k in range(count)]


def analysis_size(width: int, height: int) -> tuple[int, int]:
    """Return the size at which the frames of a width x height video are
    searched for faces: scaled down so the longer side is ANALYSIS_SIZE."""
    scale = min(1.0, ANALYSIS_SIZE / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def find_faces(
    source: Path,
    start: float,
    count: int,
    frame_size: tuple[int, int],
    detect: DetectFaces,
    *,
    cache: FaceCache | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> list[list[FaceBox]]:
    """Return the faces (or people) in count frames of source sampled from
    start seconds at SAMPLE_FPS, largest first, in the pixels of its
    frame_size frames.

    The frames are decoded by one ffmpeg run while detect searches the
    ones before (frame_stream), unless cache already has the faces of all
    of them; the faces found are put into cache, if set, and frames it
    holds are not searched again. on_progress, if set, gets the share of
    the frames done every SLICE_SAMPLES frames. A frame that ffmpeg does
    not return (past the end of the video) has no faces. Raises
    FFmpegError if ffmpeg fails.
    """
    width, height = analysis_size(*frame_size)
    scale_x, scale_y = frame_size[0] / width, frame_size[1] / height
    times = [round(start + k / SAMPLE_FPS, 3) for k in range(count)]
    known = [None if cache is None else cache.get(t) for t in times]
    report = on_progress or (lambda _: None)
    if all(found is not None for found in known):
        report(1.0)
        return [found or [] for found in known]
    faces: list[list[FaceBox]] = []
    frames = stream_frames(source, start, count, (width, height), SAMPLE_FPS)
    for k, frame in enumerate(frames):
        found = known[k]
        if found is None:
            found = [_scaled(face, scale_x, scale_y) for face in detect(frame)]
            if cache is not None:
                cache.put(times[k], found)
        faces.append(found)
        if (k + 1) % SLICE_SAMPLES == 0:
            report((k + 1) / count)
    faces += [known[k] or [] for k in range(len(faces), count)]
    report(1.0)
    return faces


def decode_frames(
    source: Path, start: float, count: int, size: tuple[int, int]
) -> npt.NDArray[np.uint8]:
    """Return up to count RGB frames of source from start seconds, sampled at
    SAMPLE_FPS and scaled to size, as an array [frame, row, column, channel]."""
    width, height = size
    result = run_ffmpeg(
        [
            "-ss", f"{start:.3f}", "-i", source, "-t", f"{count / SAMPLE_FPS:.3f}",
            "-map", "0:V:0", "-vf", f"fps={SAMPLE_FPS},scale={width}:{height}",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ]
    )  # fmt: skip
    frame_bytes = width * height * 3
    frames = len(result.stdout) // frame_bytes
    data = np.frombuffer(result.stdout, dtype=np.uint8, count=frames * frame_bytes)
    return data.reshape(frames, height, width, 3)


def _scaled(face: FaceBox, scale_x: float, scale_y: float) -> FaceBox:
    """Return face with its box scaled by scale_x and scale_y, to 0.1 pixel."""
    return face.model_copy(
        update={
            "x": round(face.x * scale_x, 1),
            "y": round(face.y * scale_y, 1),
            "width": round(face.width * scale_x, 1),
            "height": round(face.height * scale_y, 1),
        }
    )
