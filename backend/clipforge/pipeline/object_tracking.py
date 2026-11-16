"""Moving subject tracking (SPEC-v2 3.3, TASK-81): in a shot of a clip
where no face or person is seen, reframe's fill window follows the moving
object (a car, a ball, a pet) instead of holding the frame's center.

The shot's samples (10 a second, pipeline/faces) are decoded at
click_track.TRACK_SIZE, in gray and slightly blurred:

1. background: the per-pixel median of up to BACKGROUND_FRAMES samples
   spread over the shot. A moving object covers no pixel for most of the
   shot, so it drops out; this needs a still camera.
2. moving boxes: in each sample, the pixels more than DIFF_LEVEL off the
   background, opened and closed, as connected components whose box is
   MIN_AREA to MAX_AREA of the frame, largest first. A shot with a moving
   box in fewer than MIN_SEEN of its samples has no moving subject (noise,
   or a pan or zoom where everything moves).
3. tracking: the largest moving box of the shot seeds an OpenCV tracker
   (click_track.opencv_tracker: CSRT, else KCF) that follows it to the
   shot's end and, from the seed again, back to its start. If the build has
   neither, click_track.DetectorTracker follows the moving box nearest to
   the last one. A tracked box that overlaps no moving box of its sample is
   lost (the tracker drifted onto the background); its score is the share
   of it that the best overlapping moving box covers.

The boxes are FaceBox(kind="object") in source pixels, so reframe's
subject choice, gap filling and smoothing (pipeline/speaker, tracking)
treat them like a face. Shots with a face or person are left as they are.
"""

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt

from clipforge.models import FaceBox
from clipforge.pipeline.click_track import (
    Box,
    DetectorTracker,
    Tracker,
    follow_box,
    opencv_tracker,
    sliced_frames,
    track_size,
)
from clipforge.pipeline.faces import Frame, decode_frames
from clipforge.pipeline.tracking import shots

# Gray samples whose per-pixel median is a shot's background.
BACKGROUND_FRAMES = 25
# Gray levels (0-255) a pixel must differ from the background to move.
DIFF_LEVEL = 30
# A moving box's area, in fractions of the frame's.
MIN_AREA = 0.002
MAX_AREA = 0.3
# The share of a shot's samples that must have a moving box.
MIN_SEEN = 0.3
# Shots shorter than this many samples are not tracked (0.5 s).
MIN_SAMPLES = 5

Gray = npt.NDArray[np.uint8]
MakeTracker = Callable[[], Tracker | None]


def gray(frame: Frame) -> Gray:
    """Return frame (RGB) in gray, blurred over 5x5 pixels against noise."""
    plain = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    return np.asarray(cv2.GaussianBlur(plain, (5, 5), 0), dtype=np.uint8)


def background(frames: Iterator[Frame | None], count: int) -> Gray | None:
    """Return the per-pixel median of up to BACKGROUND_FRAMES of the count
    frames, evenly spread, in gray; None if none of those was decoded."""
    step = max(1, -(-count // BACKGROUND_FRAMES))
    kept = [
        gray(frame)
        for k, frame in enumerate(frames)
        if k % step == 0 and frame is not None
    ]
    if not kept:
        return None
    return np.asarray(np.median(np.stack(kept), axis=0), dtype=np.uint8)


def moving_boxes(frame: Frame, still: Gray) -> list[Box]:
    """Return the boxes of the regions of frame that differ from the
    background still (module docstring, step 2), largest first."""
    diff = cv2.absdiff(gray(frame), still)
    _, mask = cv2.threshold(diff, DIFF_LEVEL, 255, cv2.THRESH_BINARY)
    small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, small)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, large)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    frame_area = mask.shape[0] * mask.shape[1]
    boxes: list[Box] = []
    for left, top, width, height, _ in stats[1:count]:
        if MIN_AREA <= width * height / frame_area <= MAX_AREA:
            boxes.append((float(left), float(top), float(width), float(height)))
    return sorted(boxes, key=lambda box: box[2] * box[3], reverse=True)


def coverage(box: Box, moving: Sequence[Box]) -> float:
    """Return the largest share of box that one of the moving boxes covers."""
    best = 0.0
    for other in moving:
        width = min(box[0] + box[2], other[0] + other[2]) - max(box[0], other[0])
        height = min(box[1] + box[3], other[1] + other[3]) - max(box[1], other[1])
        if width > 0 and height > 0:
            best = max(best, width * height / max(box[2] * box[3], 1.0))
    return min(1.0, best)


def track_shot(
    source: Path,
    frame_size: tuple[int, int],
    times: Sequence[float],
    make: MakeTracker = opencv_tracker,
) -> list[FaceBox | None]:
    """Return the moving subject's box at each of the sample times of one
    shot of source (a frame_size video), in source pixels, or None where it
    is not seen; all None if the shot has no moving subject (module
    docstring). Raises FFmpegError if ffmpeg fails."""
    if len(times) < MIN_SAMPLES:
        return [None] * len(times)
    size = track_size(frame_size)

    def decode(start: float, count: int) -> Sequence[Frame]:
        return list(decode_frames(source, start, count, size))

    still = background(sliced_frames(decode, times), len(times))
    if still is None:
        return [None] * len(times)
    moving = [
        [] if frame is None else moving_boxes(frame, still)
        for frame in sliced_frames(decode, times)
    ]
    seen = [k for k, boxes in enumerate(moving) if boxes]
    if len(seen) < MIN_SEEN * len(times):
        return [None] * len(times)
    index = max(seen, key=lambda k: moving[k][0][2] * moving[k][0][3])
    tracked = _follow(decode, times, index, moving, still, make)
    scale_x, scale_y = frame_size[0] / size[0], frame_size[1] / size[1]
    result: list[FaceBox | None] = []
    for box, found in zip(tracked, moving, strict=True):
        score = 0.0 if box is None else coverage(box, found)
        result.append(
            None if box is None or score == 0 else _face(box, score, scale_x, scale_y)
        )
    return result


def add_objects(
    source: Path,
    frame_size: tuple[int, int],
    times: Sequence[float],
    resets: Sequence[bool],
    faces: Sequence[list[FaceBox]],
    make: MakeTracker = opencv_tracker,
) -> list[list[FaceBox]]:
    """Return faces (the faces or people in each sample at times of a
    frame_size source, with shots starting at resets) with the moving
    subject's box (track_shot) as the only box of each sample of every shot
    without faces or people where it is seen."""
    result = [list(found) for found in faces]
    for shot in shots(resets):
        if any(faces[k] for k in shot):
            continue
        boxes = track_shot(source, frame_size, [times[k] for k in shot], make)
        for k, box in zip(shot, boxes, strict=True):
            if box is not None:
                result[k] = [box]
    return result


def _follow(
    decode: Callable[[float, int], Sequence[Frame]],
    times: Sequence[float],
    index: int,
    moving: Sequence[Sequence[Box]],
    still: Gray,
    make: MakeTracker,
) -> list[Box | None]:
    """Return the box a tracker follows from the largest moving box of
    sample index forward and backward over the samples at times, in the
    pixels of the decoded frames."""
    seed = moving[index][0]
    (first,) = decode(times[index], 1)

    def detect(frame: Frame) -> list[FaceBox]:
        return [_face(box, 1.0, 1.0, 1.0) for box in moving_boxes(frame, still)]

    def tracker() -> Tracker:
        return make() or DetectorTracker(detect)

    before = sliced_frames(decode, times[:index], backward=True)
    after = sliced_frames(decode, times[index + 1 :])
    return [
        *reversed(follow_box(first, seed, before, tracker())),
        seed,
        *follow_box(first, seed, after, tracker()),
    ]


def _face(box: Box, score: float, scale_x: float, scale_y: float) -> FaceBox:
    """Return box, scaled by scale_x and scale_y to 0.1 pixel, as an object
    FaceBox with score."""
    left, top, width, height = box
    return FaceBox(
        x=round(left * scale_x, 1),
        y=round(top * scale_y, 1),
        width=round(width * scale_x, 1),
        height=round(height * scale_y, 1),
        score=round(score, 3),
        kind="object",
    )
