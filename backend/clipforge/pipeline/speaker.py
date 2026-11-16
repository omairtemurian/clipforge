"""The subject that reframe's fill window follows: the speaker (TASK-22).

The faces of a clip's samples are linked into tracks (pipeline/identity).
A track's mouth activity at a sample is the standard deviation of its
mouth openings (FaceBox.mouth) in the samples within ACTIVITY_WINDOW of it
that fall in speech; fewer than MIN_VALUES openings count as no activity.
The leader of a sample is its most active track, if that activity is at
least MIN_ACTIVITY (ties: the larger face, then the older track).

A shot starts with the leader as its subject, or else the largest face.
Another track takes over only once it has been the leader, at least
DOMINANCE times as active as the subject, for SWITCH_RUN samples in a row:
1 s of talk (SWITCH_SAMPLES) stretched by the ACTIVITY_WINDOW on each side
that its mouth moves spread over. The switch then counts from where the
mouth started to move (the first of those samples plus ACTIVITY_WINDOW), as
the whole clip is known. A subject not seen for SWITCH_SAMPLES samples
gives way to the leader, or else the largest face, from just after it was
last seen; in shorter gaps the clip has no subject (the window holds).
Size only breaks ties: a face that grows does not take over.
"""

from collections.abc import Sequence
from statistics import pstdev

from clipforge.models import FaceBox
from clipforge.pipeline.identity import track_ids

ACTIVITY_WINDOW = 5
MIN_VALUES = 3
# Lip gap over face height; a closed, still mouth stays well under this.
MIN_ACTIVITY = 0.01
DOMINANCE = 1.5
SWITCH_SAMPLES = 10
SWITCH_RUN = SWITCH_SAMPLES + 2 * ACTIVITY_WINDOW - 1


def speaking_flags(
    times: Sequence[float], speech: Sequence[tuple[float, float]] | None
) -> list[bool]:
    """Return, for each sample time, whether it is in one of the speech
    spans (start, end); every sample is if speech is None."""
    if speech is None:
        return [True] * len(times)
    return [any(start <= t <= end for start, end in speech) for t in times]


def mark_subjects(
    faces: Sequence[Sequence[FaceBox]],
    resets: Sequence[bool],
    speaking: Sequence[bool],
) -> list[list[FaceBox]]:
    """Return faces with their track ids (pipeline/identity) and the
    subject of each sample (see the module docstring) marked subject=True,
    the others False."""
    ids = track_ids(faces, resets)
    chosen = choose_subjects(faces, ids, resets, speaking)
    return [
        [
            face.model_copy(update={"track": track, "subject": track == subject})
            for face, track in zip(found, sample_ids, strict=True)
        ]
        for found, sample_ids, subject in zip(faces, ids, chosen, strict=True)
    ]


def activities(
    faces: Sequence[Sequence[FaceBox]],
    ids: Sequence[Sequence[int]],
    speaking: Sequence[bool],
) -> list[dict[int, float]]:
    """Return the mouth activity of each track seen in each sample."""
    openings: dict[int, dict[int, float]] = {}
    for sample, (found, sample_ids) in enumerate(zip(faces, ids, strict=True)):
        for face, track in zip(found, sample_ids, strict=True):
            if speaking[sample] and face.mouth is not None:
                openings.setdefault(track, {})[sample] = face.mouth
    result = []
    for sample, sample_ids in enumerate(ids):
        window = range(sample - ACTIVITY_WINDOW, sample + ACTIVITY_WINDOW + 1)
        sample_activity = {}
        for track in sample_ids:
            seen = openings.get(track, {})
            values = [seen[k] for k in window if k in seen]
            enough = len(values) >= MIN_VALUES
            sample_activity[track] = round(pstdev(values), 6) if enough else 0.0
        result.append(sample_activity)
    return result


def choose_subjects(
    faces: Sequence[Sequence[FaceBox]],
    ids: Sequence[Sequence[int]],
    resets: Sequence[bool],
    speaking: Sequence[bool],
) -> list[int | None]:
    """Return the subject's track id in each sample, None where it is not
    seen (see the module docstring)."""
    active = activities(faces, ids, speaking)
    chosen: list[int | None] = []
    current: int | None = None
    absent = 0
    pending: tuple[int, int] | None = None
    for sample, found in enumerate(faces):
        sizes = {
            track: face.width * face.height
            for face, track in zip(found, ids[sample], strict=True)
        }
        leader = _leader(active[sample], sizes)
        absent = 0 if current in sizes else absent + 1
        if resets[sample] or current is None or absent >= SWITCH_SAMPLES:
            lost = not resets[sample] and current is not None
            current, pending = None, None
            if sizes:
                current = leader if leader is not None else _largest(sizes)
                if lost:
                    # From just after the old subject was last seen.
                    chosen[sample - absent + 1 :] = [current] * (absent - 1)
                absent = 0
        else:
            subject_activity = active[sample].get(current, 0.0)
            challenger = (
                leader
                if leader is not None
                and leader != current
                and active[sample][leader] >= DOMINANCE * subject_activity
                else None
            )
            if challenger is None:
                pending = None
            elif pending is None or pending[0] != challenger:
                pending = (challenger, sample)
            if pending is not None and sample - pending[1] + 1 >= SWITCH_RUN:
                current, first = pending[0], pending[1] + ACTIVITY_WINDOW
                chosen[first:] = [current] * (sample - first)
                pending, absent = None, 0
        chosen.append(current)
    return [
        track if track in sample_ids else None
        for track, sample_ids in zip(chosen, ids, strict=True)
    ]


def _leader(active: dict[int, float], sizes: dict[int, float]) -> int | None:
    """Return the most active track (ties: the larger face, then the older
    track) if it is at least MIN_ACTIVITY active, else None."""
    if not active:
        return None
    best = min(active, key=lambda track: (-active[track], -sizes[track], track))
    return best if active[best] >= MIN_ACTIVITY else None


def _largest(sizes: dict[int, float]) -> int:
    """Return the track of the largest face (ties: the older track)."""
    return min(sizes, key=lambda track: (-sizes[track], track))
