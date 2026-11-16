"""Face tracks and motion energy of a clip for the Pro Edit signals, reusing
what the pipeline stored and computing only what is missing for the clip's
span: the job's face cache (pipeline/face_cache; frames that are not in it
are searched, and added to it) and motion.json (pipeline/visuals; if it does
not cover the clip, the clip's own span is measured and nothing is stored).
"""

import math
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from pathlib import Path

from clipforge.config import Settings
from clipforge.models import Clip, FaceBox, MotionTrack, SourceMeta
from clipforge.pipeline.face_cache import FaceCache
from clipforge.pipeline.faces import (
    DetectFaces,
    Frame,
    analysis_size,
    face_detector,
    find_faces,
    sample_times,
)
from clipforge.pipeline.motion import measure_motion, motion_spans
from clipforge.pipeline.speaker import mark_subjects, speaking_flags
from clipforge.pipeline.step import MOTION, SOURCE, load_json
from clipforge.pipeline.tracking import reset_flags
from clipforge.proedit.clock import ClipClock
from clipforge.proedit.signal_models import (
    FaceSample,
    FaceTrackSignal,
    MotionSample,
    MotionSpan,
)

# Faces are sampled 10 times a second; every FACE_STEP-th sample is kept.
FACE_STEP = 5


@contextmanager
def lazy_detector(cfg: Settings) -> Iterator[DetectFaces]:
    """Yield a face detector that loads the models of cfg only when it is
    first called, so a clip whose frames are all in the face cache never
    loads them."""
    with ExitStack() as stack:
        loaded: list[DetectFaces] = []

        def detect(frame: Frame) -> list[FaceBox]:
            if not loaded:
                loaded.append(stack.enter_context(face_detector(cfg)))
            return loaded[0](frame)

        yield detect


def face_signals(
    work: Path,
    clip: Clip,
    clock: ClipClock,
    meta: SourceMeta,
    cuts: Sequence[float],
    speech: Sequence[tuple[float, float]] | None,
    detect: DetectFaces,
) -> list[FaceTrackSignal]:
    """Return the face tracks of clip, whose job directory is work, by track.

    The faces of the clip's samples come from the job's face cache, which
    detect fills for the frames it lacks; the tracks and the subject follow
    the framing's (speaker.mark_subjects) at scene cuts cuts and speech
    spans speech (None: all the time). Samples the render does not play are
    left out.
    """
    size = (meta.width, meta.height)
    times = sample_times(clip.start, clip.end)
    cache = FaceCache(work, meta.fps, analysis_size(*size))
    try:
        faces = find_faces(
            work / SOURCE, clip.start, len(times), size, detect, cache=cache
        )
    finally:
        cache.save()
    marked = mark_subjects(
        faces, reset_flags(times, cuts), speaking_flags(times, speech)
    )
    seen: dict[int, list[float]] = defaultdict(list)
    subject: dict[int, int] = defaultdict(int)
    kept: dict[int, list[FaceSample]] = defaultdict(list)
    for index, (time, found) in enumerate(zip(times, marked, strict=True)):
        at = clock.point(time)
        if at is None:
            continue
        for face in found:
            if face.track is None:
                continue
            seen[face.track].append(at)
            subject[face.track] += face.subject
            if index % FACE_STEP == 0:
                kept[face.track].append(_sample(at, face, size))
    return [
        FaceTrackSignal(
            track=track,
            start=min(seen[track]),
            end=max(seen[track]),
            subject_share=round(subject[track] / len(seen[track]), 3),
            samples=kept[track],
        )
        for track in sorted(seen)
    ]


def _sample(at: float, face: FaceBox, size: tuple[int, int]) -> FaceSample:
    """Return face, a box in the pixels of a size frame, as a sample at at."""
    width, height = size
    return FaceSample(
        t=at,
        x=round(face.x / width, 4),
        y=round(face.y / height, 4),
        width=round(face.width / width, 4),
        height=round(face.height / height, 4),
    )


def clip_motion(
    work: Path, clip: Clip, measure: Callable[[Path, float, float], MotionTrack]
) -> MotionTrack:
    """Return the motion track of the seconds that clip spans: those of the
    job's motion.json if it covers the clip, else what measure finds in the
    clip's span of the job's source."""
    path = work / MOTION
    if path.is_file():
        stored = load_json(path, MotionTrack, "visuals")
        first = math.floor(round(clip.start - stored.start, 6))
        last = math.ceil(round(clip.end - stored.start, 6))
        if first >= 0 and last <= len(stored.scores):
            return MotionTrack(
                start=stored.start + first, scores=stored.scores[first:last]
            )
    return measure(work / SOURCE, clip.start, clip.end)


def motion_signals(
    work: Path,
    clip: Clip,
    clock: ClipClock,
    measure: Callable[[Path, float, float], MotionTrack] = measure_motion,
) -> tuple[list[MotionSample], list[MotionSpan]]:
    """Return the motion energy of each second of clip (split where the
    render cuts) and its stretches of high motion, in clip time."""
    track = clip_motion(work, clip, measure)
    samples = []
    for index, energy in enumerate(track.scores):
        begin = max(track.start + index, clip.start)
        for start, end in clock.spans(begin, min(track.start + index + 1, clip.end)):
            samples.append(MotionSample(start=start, end=end, energy=energy))
    spans = []
    for span in motion_spans(track):
        for start, end in clock.spans(span.start, span.end):
            spans.append(MotionSpan(start=start, end=end, level=span.level))
    return samples, spans
