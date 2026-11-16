"""Click-to-track (STEERING item 7b): the crop keyframes of a track scene
that follow the subject the editor clicked (or boxed) on one frame.

The scene's frames are sampled at SAMPLE_FPS, scaled so their longer side
is TRACK_SIZE pixels, and decoded slice by slice. The seed box is the one
the editor drew; a click (a seed without a size) takes the smallest face
or person box around the click on the seed frame (pipeline/detectors),
else a CLICK_BOX square centered on it. An OpenCV CSRT tracker (KCF if
the build has no CSRT; both ship with opencv-contrib-python) follows the
box from the seed frame to the scene's end, and a second one from the
seed frame back to its start, so only one slice is held at a time. If
the build has neither, the detector follows the subject: the box in each
frame nearest to the last one (DetectorTracker).

The box centers, held where the tracker lost the subject, are smoothed
like reframe's fast camera motion (tracking.follow with camera_motion.FAST:
no lag, a dead zone, a speed limit), so the picked subject is followed
closely whatever the project's camera motion, and
the keyframes keep only the samples that a straight line between their
neighbours misses by more than MAX_ERROR of the frame.
"""

from collections.abc import Callable, Iterator, Sequence
from typing import Any, Protocol

import cv2

from clipforge.models import CropPoint, FaceBox, TrackSeed
from clipforge.pipeline.camera_motion import FAST
from clipforge.pipeline.detectors import DetectFaces, Frame
from clipforge.pipeline.faces import SAMPLE_FPS, SLICE_SAMPLES, decode_frames
from clipforge.pipeline.step import StepError
from clipforge.pipeline.tracking import fill_gaps, follow

TRACK_SIZE = 320
# The side of the box tracked around a click without a subject, in frame heights.
CLICK_BOX = 0.15
# Keyframes are dropped while a line between their neighbours is this close.
MAX_ERROR = 0.005
# The detector fallback loses a subject whose box moved further than this
# many box widths between two samples.
MAX_JUMP = 2.0

# A box's left, top, width and height, in pixels.
Box = tuple[float, float, float, float]


class Tracker(Protocol):
    """An OpenCV tracker: init on a frame and box, then update per frame."""

    def init(self, image: Frame, box: tuple[int, int, int, int]) -> Any: ...

    def update(self, image: Frame) -> tuple[bool, Sequence[float]]: ...


MakeTracker = Callable[[], Tracker]


def opencv_tracker() -> Tracker | None:
    """Return a new CSRT tracker, else a KCF one, else None if the OpenCV
    build has neither (they need opencv-contrib)."""
    for name in ("TrackerCSRT", "TrackerKCF"):
        kind = getattr(cv2, name, None)
        if kind is not None and hasattr(kind, "create"):
            tracker: Tracker = kind.create()
            return tracker
    return None


class DetectorTracker:
    """A tracker that follows the face or person box nearest to the last
    one that detect finds in each frame (the fallback without CSRT/KCF)."""

    def __init__(self, detect: DetectFaces) -> None:
        self._detect = detect
        self._box: Box = (0, 0, 0, 0)

    def init(self, image: Frame, box: tuple[int, int, int, int]) -> None:
        """Start from box on image."""
        self._box = _as_box(box)

    def update(self, image: Frame) -> tuple[bool, Sequence[float]]:
        """Return (True, box) of the detection nearest the last box in
        image, or (False, last box) if none is within MAX_JUMP widths."""
        found = [_face_box(face) for face in self._detect(image)]
        if not found:
            return False, self._box
        nearest = min(found, key=lambda box: _distance(box, self._box))
        if _distance(nearest, self._box) > MAX_JUMP * max(self._box[2], 1.0):
            return False, self._box
        self._box = nearest
        return True, nearest


def track_size(frame_size: tuple[int, int]) -> tuple[int, int]:
    """Return the even size that frames of a frame_size video are tracked
    at: scaled so the longer side is at most TRACK_SIZE."""
    width, height = frame_size
    scale = min(1.0, TRACK_SIZE / max(width, height))
    return max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)


def seed_box(seed: TrackSeed, faces: Sequence[FaceBox], size: tuple[int, int]) -> Box:
    """Return the box to track, in the pixels of a size (width, height)
    frame: seed's own box if it has a size, else the smallest of faces
    around the click, else a CLICK_BOX square centered on the click and
    kept inside the frame."""
    width, height = size
    if seed.width > 0 and seed.height > 0:
        return (
            seed.x * width,
            seed.y * height,
            seed.width * width,
            seed.height * height,
        )
    x, y = seed.x * width, seed.y * height
    around = [
        face
        for face in faces
        if face.x <= x <= face.x + face.width and face.y <= y <= face.y + face.height
    ]
    if around:
        return _face_box(min(around, key=lambda face: face.width * face.height))
    side = CLICK_BOX * height
    left = min(max(x - side / 2, 0.0), width - side)
    top = min(max(y - side / 2, 0.0), height - side)
    return (left, top, side, side)


def follow_box(
    first: Frame, box: Box, frames: Iterator[Frame | None], tracker: Tracker
) -> list[Box | None]:
    """Return the box that tracker follows from box on first in each of
    frames, in order; None where it lost the subject or a frame is missing."""
    left, top, width, height = (round(v) for v in box)
    tracker.init(first, (left, top, width, height))
    boxes: list[Box | None] = []
    for frame in frames:
        if frame is None:
            boxes.append(None)
            continue
        ok, found = tracker.update(frame)
        boxes.append(_as_box(found) if ok else None)
    return boxes


def smooth_points(
    times: Sequence[float],
    boxes: Sequence[Box | None],
    size: tuple[int, int],
    seed: Box,
) -> list[CropPoint]:
    """Return the crop keyframes that follow the centers of boxes (in the
    pixels of a size frame) at times: gaps held (tracking.fill_gaps from the
    seed box's center), smoothed (tracking.follow), in frame fractions to
    4 digits, simplified to within MAX_ERROR (simplify)."""
    width, height = size
    resets = [False] * len(times)
    xs = [None if box is None else box[0] + box[2] / 2 for box in boxes]
    ys = [None if box is None else box[1] + box[3] / 2 for box in boxes]
    seed_x, seed_y = seed[0] + seed[2] / 2, seed[1] + seed[3] / 2
    path_x = follow(fill_gaps(xs, resets, seed_x), resets, width, FAST)
    path_y = follow(fill_gaps(ys, resets, seed_y), resets, height, FAST)
    points = [
        CropPoint(t=t, x=_fraction(x, width), y=_fraction(y, height))
        for t, x, y in zip(times, path_x, path_y, strict=True)
    ]
    return simplify(points)


def simplify(points: Sequence[CropPoint], error: float = MAX_ERROR) -> list[CropPoint]:
    """Return points without those that a straight line between the kept
    neighbours misses by at most error in x and y (Ramer-Douglas-Peucker);
    the first and the last are always kept."""
    if len(points) < 3:
        return list(points)
    keep = {0, len(points) - 1}
    spans = [(0, len(points) - 1)]
    while spans:
        first, last = spans.pop()
        worst, worst_error = -1, error
        for k in range(first + 1, last):
            miss = _miss(points[first], points[last], points[k])
            if miss > worst_error:
                worst, worst_error = k, miss
        if worst >= 0:
            keep.add(worst)
            spans += [(first, worst), (worst, last)]
    return [points[k] for k in sorted(keep)]


def sliced_frames(
    decode: Callable[[float, int], Sequence[Frame]],
    times: Sequence[float],
    backward: bool = False,
) -> Iterator[Frame | None]:
    """Yield the frames at times (in reverse order if backward), decoded
    SLICE_SAMPLES at a time by decode(start, count); None for a frame that
    decode did not return."""
    starts = list(range(0, len(times), SLICE_SAMPLES))
    for first in reversed(starts) if backward else starts:
        count = min(SLICE_SAMPLES, len(times) - first)
        frames = decode(times[first], count)
        part = [frames[k] if k < len(frames) else None for k in range(count)]
        yield from reversed(part) if backward else part


def resolved_seed(seed: TrackSeed, box: Box, size: tuple[int, int]) -> TrackSeed:
    """Return seed with box (in the pixels of a size frame) as its box, in
    frame fractions to 4 digits."""
    width, height = size
    return TrackSeed(
        t=seed.t,
        x=_fraction(box[0], width),
        y=_fraction(box[1], height),
        width=_fraction(box[2], width),
        height=_fraction(box[3], height),
    )


def track_scene(
    source: Any,
    frame_size: tuple[int, int],
    times: Sequence[float],
    seed: TrackSeed,
    detect: DetectFaces | None,
    make: Callable[[], Tracker | None] = opencv_tracker,
) -> tuple[list[CropPoint], TrackSeed]:
    """Return the crop keyframes at the sample times of a scene of source
    (a frame_size video) that follow the subject seed marks, and the seed
    with the box tracked (module docstring). detect finds the faces that a
    click picks from (None: none) and follows them if make has no tracker.

    Raises StepError if the seed frame cannot be decoded or there is no
    tracker, and FFmpegError if ffmpeg fails."""
    size = track_size(frame_size)
    index = min(len(times) - 1, max(0, round((seed.t - times[0]) * SAMPLE_FPS)))

    def decode(start: float, count: int) -> Sequence[Frame]:
        return list(decode_frames(source, start, count, size))

    first = decode(times[index], 1)
    if not first:
        raise StepError(f"no frame of the source at {times[index]:.3f} s")
    faces = detect(first[0]) if detect is not None and not seed.width else []
    box = seed_box(seed, faces, size)

    def tracker() -> Tracker:
        found = make()
        if found is not None:
            return found
        if detect is None:
            raise StepError("no OpenCV tracker and no face detector to track with")
        return DetectorTracker(detect)

    before = sliced_frames(decode, times[:index], backward=True)
    after = sliced_frames(decode, times[index + 1 :])
    boxes = [
        *reversed(follow_box(first[0], box, before, tracker())),
        box,
        *follow_box(first[0], box, after, tracker()),
    ]
    return smooth_points(times, boxes, size, box), resolved_seed(seed, box, size)


def _as_box(values: Sequence[float]) -> Box:
    """Return the first four values as a box, in float pixels."""
    left, top, width, height = (float(v) for v in values[:4])
    return (left, top, width, height)


def _face_box(face: FaceBox) -> Box:
    """Return face's box."""
    return (face.x, face.y, face.width, face.height)


def _distance(a: Box, b: Box) -> float:
    """Return the distance between the centers of boxes a and b."""
    dx = (a[0] + a[2] / 2) - (b[0] + b[2] / 2)
    dy = (a[1] + a[3] / 2) - (b[1] + b[3] / 2)
    return float((dx * dx + dy * dy) ** 0.5)


def _fraction(value: float, size: int) -> float:
    """Return value pixels as a fraction of size, in [0, 1], to 4 digits."""
    return round(min(1.0, max(0.0, value / size)), 4)


def _miss(first: CropPoint, last: CropPoint, point: CropPoint) -> float:
    """Return how far point is, in x or y, from the line first-last at its t."""
    share = (point.t - first.t) / (last.t - first.t) if last.t > first.t else 0.0
    x = first.x + (last.x - first.x) * share
    y = first.y + (last.y - first.y) * share
    return max(abs(point.x - x), abs(point.y - y))
