"""Motion spread (TASK-198, rule "motion" of pipeline/zoom_out_rules): how
much of the frame's width moves, for a clip's span of the source.

The span is decoded as pipeline/motion does (motion.read_frames: SAMPLE_FPS
small grey frames a second). For each pair of consecutive frames, a column
of pixels moves when the mean absolute difference of its pixels is at least
COLUMN_ENERGY of full scale; the pair's spread is the share of columns that
move, at the later frame's time. A pair across a scene cut has spread 0, as
the cut changes every column without anything moving.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from clipforge.pipeline.motion import HEIGHT, SAMPLE_FPS, WIDTH, read_frames
from clipforge.pipeline.zoom_out_rules import MotionSample

COLUMN_ENERGY = 0.04


def motion_spread(
    video: Path, start: float, end: float, cuts: Sequence[float] = ()
) -> list[MotionSample]:
    """Return the motion spread of each frame pair of start to end seconds
    of video (module docstring), with scene cuts at cuts. Raises StepError
    if the video cannot be decoded."""
    frames = read_frames(video, start, end).reshape(-1, HEIGHT, WIDTH)
    samples = []
    for index in range(1, len(frames)):
        before = start + (index - 1) / SAMPLE_FPS
        t = start + index / SAMPLE_FPS
        if any(before < cut <= t for cut in cuts):
            samples.append(MotionSample(round(t, 3), 0.0))
            continue
        pair = frames[index - 1 : index + 1].astype(np.int16)
        columns = np.abs(pair[1] - pair[0]).mean(axis=0) / 255
        spread = float(np.mean(columns >= COLUMN_ENERGY))
        samples.append(MotionSample(round(t, 3), round(spread, 4)))
    return samples
