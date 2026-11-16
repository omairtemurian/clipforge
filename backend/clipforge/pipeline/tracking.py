"""Tracking of reframe (SPEC 6.8, TASK-22): crop windows that follow faces.

The faces in each sample of a clip (10 frames a second, pipeline/faces)
give one center x per sample for a window to follow: the subject's
(pipeline/speaker; the largest face's in plans made before subjects were
marked) for the fill layout, the left and the right of the two largest
faces for the two windows of the split layout. A window follows its
centers shot by shot (a scene cut starts a new shot, where the window
jumps):

- subject changes: when the subject changes (another track) in a shot,
  the samples between the old subject's last center and the new one's
  first take the new one's, so the window heads for it without waiting;
- gaps: a gap of fewer than HOLD_SAMPLES samples without a center holds
  the center before it; in a longer one the window moves evenly from the
  center before it to the one after it. The samples of a shot before its
  first center take that center, those after its last hold it, and a shot
  without centers holds the last center of the shots before it, or a
  default if there was none yet;
- the path is smoothed without lag and the window moves along it as the
  project's camera motion says (pipeline/camera_motion): calm and normal
  rest in a dead-zone and re-aim in eased moves, fast holds in a dead-zone
  and pans at a capped speed.
"""

from bisect import bisect_left
from collections.abc import Iterable, Sequence

from clipforge.models import FaceBox
from clipforge.pipeline.camera_motion import CALM, Motion, shot_path
from clipforge.pipeline.faces import SAMPLE_FPS

# Gaps shorter than this (1 s) hold the center before them.
HOLD_SAMPLES = SAMPLE_FPS

FacePair = tuple[FaceBox, FaceBox]


def reset_flags(times: Sequence[float], cuts: Iterable[float]) -> list[bool]:
    """Return, for each of the sorted sample times, whether a shot starts
    there: at the first sample and the first sample at or after a cut."""
    flags = [k == 0 for k in range(len(times))]
    for cut in cuts:
        k = bisect_left(times, cut)
        if k < len(times):
            flags[k] = True
    return flags


def center_x(face: FaceBox) -> float:
    """Return the x of the center of face."""
    return face.x + face.width / 2


def subject_centers(faces: Sequence[Sequence[FaceBox]]) -> list[float | None]:
    """Return the center x of the subject of each sample, or None for a
    sample without one. If no face is marked as a subject (a plan made
    before subjects were), the largest face of each sample is."""
    marked = any(face.subject for found in faces for face in found)
    centers: list[float | None] = []
    for found in faces:
        if marked:
            subject = next((face for face in found if face.subject), None)
        else:
            subject = max(found, key=_area, default=None)
        centers.append(None if subject is None else center_x(subject))
    return centers


def subject_tracks(faces: Sequence[Sequence[FaceBox]]) -> list[int | None]:
    """Return the track id of the face marked subject in each sample, or
    None for a sample without one or a subject without a track."""
    return [
        next((face.track for face in found if face.subject), None) for found in faces
    ]


def bridge_switches(
    centers: Sequence[float | None],
    tracks: Sequence[int | None],
    resets: Sequence[bool],
) -> list[float | None]:
    """Return centers with each gap in a shot between the centers of two
    different subject tracks filled with the center after it (see the
    subject changes in the module docstring)."""
    bridged = list(centers)
    for shot in shots(resets):
        known = [k for k in shot if centers[k] is not None]
        for before, after in zip(known, known[1:], strict=False):
            old, new = tracks[before], tracks[after]
            if old is not None and new is not None and old != new:
                bridged[before + 1 : after] = [centers[after]] * (after - before - 1)
    return bridged


def face_pairs(faces: Sequence[Sequence[FaceBox]]) -> list[FacePair | None]:
    """Return the two largest faces (not people) of each sample, the left one
    first, or None for a sample with fewer than two faces."""
    return [
        None if group is None else (group[0], group[1])
        for group in face_groups(faces, 2)
    ]


def face_groups(
    faces: Sequence[Sequence[FaceBox]], count: int
) -> list[tuple[FaceBox, ...] | None]:
    """Return the count largest faces (not people) of each sample, from left
    to right, or None for a sample with fewer than count faces."""
    groups: list[tuple[FaceBox, ...] | None] = []
    for sample in faces:
        found = [face for face in sample if face.kind == "face"]
        if len(found) < count:
            groups.append(None)
            continue
        largest = sorted(found, key=_area, reverse=True)[:count]
        groups.append(tuple(sorted(largest, key=center_x)))
    return groups


def shots(resets: Sequence[bool]) -> list[range]:
    """Return the sample ranges of the shots that start at each reset (and
    at the first sample)."""
    starts = [k for k, reset in enumerate(resets) if reset or k == 0]
    return [
        range(first, stop)
        for first, stop in zip(starts, [*starts[1:], len(resets)], strict=True)
    ]


def fill_gaps(
    centers: Sequence[float | None], resets: Sequence[bool], default: float
) -> list[float]:
    """Return centers with each None replaced by the center to aim at (see
    the gaps in the module docstring)."""
    filled: list[float] = []
    last = default
    for shot in shots(resets):
        known = [k for k in shot if centers[k] is not None]
        if not known:
            filled.extend([last] * len(shot))
            continue
        values = [float(centers[k] or 0.0) for k in known]
        for k in shot:
            filled.append(_gap_center(k, known, values))
        last = filled[-1]
    return filled


def follow(
    targets: Sequence[float],
    resets: Sequence[bool],
    frame_width: int,
    motion: Motion = CALM,
    crop_width: int | None = None,
) -> list[float]:
    """Return the window center at each sample of a frame_width video,
    following targets shot by shot with motion (camera_motion.shot_path;
    its catch-up needs crop_width, the window's width)."""
    centers: list[float] = []
    for shot in shots(resets):
        path = [targets[k] for k in shot]
        centers.extend(shot_path(path, frame_width, motion, crop_width))
    return centers


def track_centers(
    centers: Sequence[float | None],
    resets: Sequence[bool],
    frame_width: int,
    crop_width: int,
    default: float,
    motion: Motion = CALM,
) -> list[int]:
    """Return the left edge x of a crop_width window of a frame_width video
    that follows the center x of each sample (None: no center; the first
    shots without one take default).

    The window stays inside the frame (centers nearer to an edge than half
    the window are aimed at as if they were not), and x is rounded down to
    an even pixel, like render.center_crop's, for yuv420p video. The
    window moves with motion (follow).
    """
    half = crop_width / 2
    targets = [
        min(frame_width - half, max(half, center))
        for center in fill_gaps(centers, resets, default)
    ]
    xs = []
    for center in follow(targets, resets, frame_width, motion, crop_width):
        x = min(frame_width - crop_width, max(0, round(center - half)))
        xs.append(x - x % 2)
    return xs


def track_subject(
    faces: Sequence[Sequence[FaceBox]],
    resets: Sequence[bool],
    frame_width: int,
    crop_width: int,
    motion: Motion = CALM,
) -> list[int]:
    """Return the left edge x of a crop_width window that follows the subject
    (subject_centers) in the faces of each sample of a frame_width video; it
    holds the frame center until a subject is seen (track_centers, with
    motion)."""
    centers = bridge_switches(subject_centers(faces), subject_tracks(faces), resets)
    return track_centers(
        centers, resets, frame_width, crop_width, frame_width / 2, motion
    )


def _gap_center(sample: int, known: Sequence[int], values: Sequence[float]) -> float:
    """Return the center at sample of a shot whose samples known (sorted)
    have the centers values: its own, the first's before the first, the
    last's after the last, and in a gap the one before it if the gap is
    shorter than HOLD_SAMPLES, else the line between the two around it."""
    k = bisect_left(known, sample)
    if k < len(known) and known[k] == sample:
        return values[k]
    if k == 0:
        return values[0]
    if k == len(known):
        return values[-1]
    before, after = known[k - 1], known[k]
    if after - before - 1 < HOLD_SAMPLES:
        return values[k - 1]
    share = (sample - before) / (after - before)
    return values[k - 1] + share * (values[k] - values[k - 1])


def _area(face: FaceBox) -> float:
    """Return the area of face in square pixels."""
    return face.width * face.height
