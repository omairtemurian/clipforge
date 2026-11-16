"""Tests of the windows of the grid and pip layouts (pipeline/layout_windows,
SPEC-v2 3.3): which faces they follow, their size, and how framing adds
them to a crop plan made before them."""

from pathlib import Path

import pytest
from builders import make_clip, plan_at, source_meta
from clipforge.models import FaceBox, SceneReframe, SignalList
from clipforge.pipeline.framing import framed_plan
from clipforge.pipeline.layout_windows import (
    add_layout_windows,
    grid_windows,
    inset_window,
    other_faces,
)
from clipforge.pipeline.reframe import ClipSpan, crop_path, plan_crop
from clipforge.pipeline.step import META, SIGNALS, StepError, write_json
from clipforge.pipeline.tracking import face_groups

FRAME = (1280, 720)
CLIP = ClipSpan(7, 10.0, 12.0)


def face(
    center_x: float, size: float = 100.0, kind: str = "face", subject: bool = False
) -> FaceBox:
    """Return a size px face (or kind) centered at center_x, 300."""
    half = size / 2
    return FaceBox.model_validate(
        {
            "x": center_x - half,
            "y": 300 - half,
            "width": size,
            "height": size,
            "score": 0.9,
            "kind": kind,
            "subject": subject,
        }
    )


def test_face_groups_are_the_largest_faces_from_left_to_right() -> None:
    big, small, tiny = face(900, 200), face(100, 150), face(500, 50)
    person = face(300, 400, kind="person")

    groups = face_groups([[big, small, tiny, person], [big, person]], 2)

    assert groups == [(small, big), None]
    assert face_groups([[big, small, tiny]], 3) == [(small, tiny, big)]


def test_grid_windows_follow_the_left_middle_and_right_face() -> None:
    faces = [[face(1067), face(213), face(640)] for _ in range(10)]
    resets = [k == 0 for k in range(10)]

    windows = grid_windows(faces, resets, FRAME, "9:16")

    # 1080x640 cells: the largest such window in 426 px is 426x252.
    assert [(w.width, w.height) for w in windows] == [(426, 252)] * 3
    assert [w.xs[0] for w in windows] == [0, 426, 854]
    assert [w.y for w in windows] == [174] * 3


def test_grid_windows_without_three_faces_take_the_thirds() -> None:
    faces = [[face(213), face(640)] for _ in range(5)]

    windows = grid_windows(faces, [True] + [False] * 4, FRAME, "1:1")

    # 360x1080 cells: 240x720 windows centered on each third of the frame.
    assert [(w.width, w.height, w.y) for w in windows] == [(240, 720, 0)] * 3
    assert [w.xs for w in windows] == [[92] * 5, [520] * 5, [946] * 5]


def test_other_faces_skip_the_subject_or_else_the_largest() -> None:
    left, right = face(200, 200), face(1000, 100, subject=True)
    unmarked = [face(200, 200), face(1000, 100)]

    others = other_faces([[left, right], unmarked, [left], []])

    assert others == [left, unmarked[1], None, None]


def test_the_inset_follows_the_other_face_at_three_times_its_height() -> None:
    faces = [[face(200, 200, subject=True), face(1000, 80)] for _ in range(5)]
    resets = [True] + [False] * 4

    window = inset_window(faces, resets, FRAME)

    assert window is not None
    assert (window.width, window.height, window.y) == (240, 240, 180)
    assert window.xs == [880] * 5
    big = [[face(200, 300), face(1000, 300)] for _ in range(5)]
    large = inset_window(big, resets, FRAME)
    assert large is not None and large.width == 640


def test_no_inset_window_without_another_face() -> None:
    faces = [[face(640, kind="person")], [face(640)], []]

    assert inset_window(faces, [True, False, False], FRAME) is None


def test_add_layout_windows_rebuilds_the_windows_of_an_older_plan() -> None:
    faces = [[face(213), face(640, subject=True), face(1067)] for _ in range(20)]
    plan = plan_crop(CLIP, "9:16", FRAME, faces, [])
    older = plan.model_copy(update={"grid": [], "inset": None})

    added = add_layout_windows(older, FRAME, [])

    assert len(plan.grid) == 3 and plan.inset is not None
    assert (added.grid, added.inset) == (plan.grid, plan.inset)
    assert added.keyframes == plan.keyframes
    assert add_layout_windows(plan, FRAME, []) is plan


@pytest.fixture
def work(tmp_path: Path) -> Path:
    """A job directory with meta.json (1280x720), no signals and clip 7's
    crop plan, made before the grid and pip layouts."""
    write_json(tmp_path / META, source_meta())
    write_json(tmp_path / SIGNALS, SignalList([]))
    write_json(crop_path(tmp_path, 7), plan_at(400, 400))
    return tmp_path


def test_framing_adds_the_windows_when_the_clip_uses_grid_or_pip(
    work: Path,
) -> None:
    pip_scene = SceneReframe(start=10.0, end=11.0, layout="pip")
    fill_scene = SceneReframe(start=11.0, end=12.5)

    plain = framed_plan(work, make_clip("karaoke_bold"))
    grid = framed_plan(work, make_clip("karaoke_bold", layout="grid"))
    scened = framed_plan(
        work, make_clip("karaoke_bold", scene_reframes=[pip_scene, fill_scene])
    )

    assert (plain.grid, plain.inset) == ([], None)
    # No faces: the windows hold the thirds; no other face, no inset.
    assert [w.xs for w in grid.grid] == [[0, 0], [426, 426], [854, 854]]
    assert grid.inset is None and len(scened.grid) == 3
    assert [k.x for k in grid.keyframes] == [400, 400]


def test_framing_an_older_plan_in_grid_needs_the_scene_cuts(work: Path) -> None:
    (work / SIGNALS).unlink()

    with pytest.raises(StepError, match="signals"):
        framed_plan(work, make_clip("karaoke_bold", layout="grid"))
