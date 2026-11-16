"""Identities of reframe's faces across the samples of a clip (TASK-22).

Each face (or person) of a sample is matched to a track of the samples
before it by the distance of their centers: a box joins the track whose
last box is nearest, if that is at most MAX_SHIFT times the larger of the
two boxes' widths and they are of the same kind; the nearest pairs are
matched first. A track not seen for more than MAX_GAP samples ends, and
every track ends at a reset (a scene cut starts a new shot). A box that
joins no track starts a new one; tracks are numbered from 0 in order of
appearance.
"""

from collections.abc import Sequence
from typing import NamedTuple

from clipforge.models import FaceBox

# The farthest a face moves from one sample to the next, in face widths.
MAX_SHIFT = 1.0
# Samples a track may go unseen (1 s at 10 samples a second).
MAX_GAP = 10


class _Track(NamedTuple):
    """The last box of a track, and the sample it was seen in."""

    box: FaceBox
    sample: int


def track_ids(
    faces: Sequence[Sequence[FaceBox]], resets: Sequence[bool]
) -> list[list[int]]:
    """Return the track id of each face of each sample (see the module
    docstring), in the order of the faces."""
    tracks: dict[int, _Track] = {}
    next_id = 0
    ids: list[list[int]] = []
    for sample, (found, reset) in enumerate(zip(faces, resets, strict=True)):
        if reset:
            tracks.clear()
        live = {
            track_id: track
            for track_id, track in tracks.items()
            if sample - track.sample <= MAX_GAP + 1
        }
        matched = _match(live, found)
        sample_ids = []
        for index, box in enumerate(found):
            track_id = matched.get(index)
            if track_id is None:
                track_id, next_id = next_id, next_id + 1
            tracks[track_id] = _Track(box, sample)
            sample_ids.append(track_id)
        ids.append(sample_ids)
    return ids


def _match(tracks: dict[int, _Track], found: Sequence[FaceBox]) -> dict[int, int]:
    """Return the track id that each box of found joins, by its index; the
    nearest pairs first, ties by track id and then box index."""
    pairs = []
    for track_id, track in tracks.items():
        for index, box in enumerate(found):
            cost = _shift(track.box, box)
            if box.kind == track.box.kind and cost <= MAX_SHIFT:
                pairs.append((cost, track_id, index))
    matched: dict[int, int] = {}
    used: set[int] = set()
    for _, track_id, index in sorted(pairs):
        if index not in matched and track_id not in used:
            matched[index] = track_id
            used.add(track_id)
    return matched


def _shift(before: FaceBox, after: FaceBox) -> float:
    """Return the distance between the centers of two boxes, in widths of
    the wider one."""
    dx = (after.x + after.width / 2) - (before.x + before.width / 2)
    dy = (after.y + after.height / 2) - (before.y + before.height / 2)
    width = max(before.width, after.width, 1.0)
    return float((dx * dx + dy * dy) ** 0.5 / width)
