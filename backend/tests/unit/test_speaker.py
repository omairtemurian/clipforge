"""Tests of reframe's speaker-aware subject choice (pipeline/speaker): mouth
activity in speech, the 1 s hysteresis, gaps and the largest-face tie-break."""

import pytest
from clipforge.models import FaceBox
from clipforge.pipeline.identity import track_ids
from clipforge.pipeline.speaker import (
    activities,
    choose_subjects,
    mark_subjects,
    speaking_flags,
)

SILENT, OPEN = 0.02, 0.08


def face(center_x: float, size: float = 100.0, mouth: float | None = None) -> FaceBox:
    """Return a square face of size centered at center_x with mouth open."""
    return FaceBox(
        x=center_x - size / 2,
        y=300.0,
        width=size,
        height=size,
        score=0.9,
        mouth=mouth,
    )


def two_faces(talks: range, count: int = 40) -> list[list[FaceBox]]:
    """Return count samples of a large silent face A at x 300 and a smaller
    face B at x 900 whose mouth opens and closes in the samples talks."""
    return [
        [
            face(300, 150, SILENT),
            face(900, 100, (SILENT, OPEN)[k % 2] if k in talks else SILENT),
        ]
        for k in range(count)
    ]


def subjects(faces: list[list[FaceBox]], speaking: bool = True) -> list[int | None]:
    """Return the subject track of each sample of one shot of faces."""
    resets = [True] + [False] * (len(faces) - 1)
    ids = track_ids(faces, resets)
    return choose_subjects(faces, ids, resets, [speaking] * len(faces))


def test_the_face_that_speaks_takes_over_from_where_it_started() -> None:
    faces = two_faces(range(10, 40))

    # B (track 1) talks from sample 10; its activity (the spread of its
    # mouth openings within 0.5 s) leads from sample 6, and after 1 s of
    # dominance it takes over from sample 11.
    assert subjects(faces) == [0] * 11 + [1] * 29
    activity = [
        round(sample[1], 4)
        for sample in activities(
            faces, track_ids(faces, [True] + [False] * 39), [True] * 40
        )
    ]
    assert activity[:10] == [0.0] * 6 + [0.0172, 0.0172, 0.0231, 0.0231]
    assert activity[14] == pytest.approx(0.0299, abs=1e-4)


@pytest.mark.parametrize(("talk", "takes_over"), [(9, False), (10, True)])
def test_a_speaker_must_dominate_for_a_second_to_take_over(
    talk: int, takes_over: bool
) -> None:
    chosen = subjects(two_faces(range(10, 10 + talk), count=50))

    assert (1 in chosen) is takes_over


def test_mouth_moves_outside_speech_do_not_count() -> None:
    assert subjects(two_faces(range(10, 40)), speaking=False) == [0] * 40


def test_a_subject_unseen_for_less_than_a_second_is_kept() -> None:
    # A (track 0) is gone for 5 samples; B grows larger than A meanwhile.
    faces = [
        ([] if 3 <= k < 8 else [face(300, 150)]) + [face(900, 100 + 10 * k)]
        for k in range(12)
    ]

    assert subjects(faces) == [0, 0, 0] + [None] * 5 + [0] * 4


def test_a_subject_unseen_for_a_second_gives_way_to_the_largest_face() -> None:
    faces = [
        ([] if 2 <= k < 14 else [face(300, 150)]) + [face(900, 100)] for k in range(16)
    ]

    # A is unseen from sample 2; at sample 11 (10 samples) B takes over,
    # from sample 2 on as the whole clip is known, and keeps it when A comes
    # back (as track 2).
    assert subjects(faces) == [0, 0] + [1] * 14


def test_mark_subjects_marks_one_face_per_sample() -> None:
    faces = two_faces(range(10, 40))

    marked = mark_subjects(faces, [True] + [False] * 39, [True] * 40)

    assert [[f.subject for f in found] for found in marked] == (
        [[True, False]] * 11 + [[False, True]] * 29
    )
    assert [[f.track for f in found] for found in marked] == [[0, 1]] * 40
    unmarked = marked[0][0].model_copy(update={"subject": False, "track": None})
    assert unmarked == faces[0][0]


def test_speaking_flags_mark_the_samples_in_speech() -> None:
    times = [1.0, 1.1, 1.5, 2.0, 2.6]

    assert speaking_flags(times, [(1.05, 1.5), (2.5, 3.0)]) == [
        False,
        True,
        True,
        False,
        True,
    ]
    assert speaking_flags(times, None) == [True] * 5
