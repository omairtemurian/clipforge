"""Tests of the identities of reframe's faces across samples
(pipeline/identity): matching by center distance, gaps and resets."""

from clipforge.models import FaceBox
from clipforge.pipeline.identity import track_ids


def face(center_x: float, kind: str = "face") -> FaceBox:
    """Return a 100 px square face (or person) centered at center_x."""
    return FaceBox(
        x=center_x - 50,
        y=300.0,
        width=100.0,
        height=100.0,
        score=0.9,
        kind="person" if kind == "person" else "face",
    )


def test_faces_keep_their_ids_in_any_order_and_new_ones_get_new_ids() -> None:
    faces = [
        [face(300), face(800)],
        [face(810), face(305)],  # listed the other way round
        [face(820)],  # 0 is not seen
        [],
        [face(330), face(830)],  # 0 is back within the gap
        [face(340, "person")],  # a person is not a face
        [face(500)],  # too far from every track
    ]

    ids = track_ids(faces, [True] + [False] * 6)

    assert ids == [[0, 1], [1, 0], [1], [], [0, 1], [2], [3]]


def test_a_track_ends_after_a_second_unseen_and_at_a_reset() -> None:
    seen_after = [[face(300)]] + [[]] * 10 + [[face(300)]]
    lost_after = [[face(300)]] + [[]] * 11 + [[face(300)]]

    # 10 samples unseen keep the track; 11 end it.
    assert track_ids(seen_after, [True] + [False] * 11)[-1] == [0]
    assert track_ids(lost_after, [True] + [False] * 12)[-1] == [1]
    # A scene cut starts new tracks for the same place.
    assert track_ids([[face(300)]] * 3, [True, False, True]) == [[0], [0], [1]]
