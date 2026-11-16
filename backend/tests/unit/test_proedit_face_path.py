"""Unit tests of the subject's face in each frame of a Pro Edit render
(proedit/render/face_path.py, TASK-209): the face box of the crop plan in
the fill window, moved between keyframes of the same track, held through
freeze frames, slowed by speed ramps and slow motion (TASK-210) and mapped
through cuts; the tracked object likewise (TASK-212)."""

from dataclasses import astuple
from pathlib import Path

import pytest
from clipforge.models import CropKeyframe, CropPlan, FaceBox
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.scene_graph import ScenePart
from clipforge.proedit.edl import TypedEdlItem, parse_item
from clipforge.proedit.render.base import ProEditBase
from clipforge.proedit.render.canvas import Box, Canvas
from clipforge.proedit.render.face_path import (
    PlanFaces,
    source_times,
    subject_faces,
    tracked_object,
)
from clipforge.proedit.render.graph import canvas_of
from edl_fakes import item


def face(x: float, track: int, subject: bool = True, kind: str = "face") -> FaceBox:
    return FaceBox.model_validate(
        {
            "x": x,
            "y": 360,
            "width": 72,
            "height": 144,
            "score": 1.0,
            "kind": kind,
            "track": track,
            "subject": subject,
        }
    )


def fill_plan() -> CropPlan:
    """A 404 x 720 fill window of a 1280 x 720 source over 1..5 s whose
    keyframes say where the subject's face is."""
    times = sample_times(1.0, 5.0)
    faces = [[FaceBox(x=600, y=300, width=64, height=64, score=1.0)] for _ in times]
    plan = plan_crop(ClipSpan(7, 1.0, 5.0), "9:16", (1280, 720), faces, [])
    keyframes = [
        CropKeyframe(t=1.0, x=400, faces=[face(300, 2, False, "person"), face(500, 0)]),
        CropKeyframe(t=2.0, x=500, faces=[face(700, 1, False), face(600, 0)]),
        CropKeyframe(t=3.0, x=500, faces=[face(700, 1)]),
        CropKeyframe(t=4.0, x=500, faces=[face(0, 1, False, "object")]),
    ]
    return plan.model_copy(update={"keyframes": keyframes, "y": 0})


def box(x: float, left: float) -> tuple[float, ...]:
    """The edges of the face at x in the window from left."""
    return (x - left) / 404, 0.5, (x + 72 - left) / 404, 0.7


def edges(found: Box | None) -> tuple[float, ...] | None:
    return None if found is None else astuple(found)


def test_the_window_holds_the_subject_moved_between_keyframes() -> None:
    faces = PlanFaces(fill_plan())
    assert edges(faces.at(1.0)) == pytest.approx(box(500, 400))
    assert edges(faces.at(1.5)) == pytest.approx(box(550, 450))
    assert edges(faces.at(0.5)) == pytest.approx(box(500, 400))


def test_a_new_track_jumps_at_the_nearer_keyframe_and_no_face_is_none() -> None:
    faces = PlanFaces(fill_plan())
    assert edges(faces.at(2.4)) == pytest.approx(box(600, 500))
    assert edges(faces.at(2.6)) == pytest.approx(box(700, 500))
    assert faces.at(3.6) is None
    assert faces.at(9.0) is None


def test_a_face_past_the_window_is_clamped_to_it() -> None:
    plan = fill_plan()
    edge = CropKeyframe(t=1.0, x=400, faces=[face(780, 0)])
    faces = PlanFaces(plan.model_copy(update={"keyframes": [edge]}))
    found = faces.at(1.0)
    assert found is not None
    assert found.left == pytest.approx(380 / 404) and found.right == 1.0
    gone = CropKeyframe(t=1.0, x=400, faces=[face(900, 0)])
    assert PlanFaces(plan.model_copy(update={"keyframes": [gone]})).at(1.0) is None


def test_frames_map_through_cuts_and_hold_through_freezes() -> None:
    plan = fill_plan()
    base = ProEditBase(Path("s.mp4"), 1.0, 5.0, plan, "fill", cut_ranges=((2.0, 3.0),))
    times = source_times(base, 10)
    assert len(times) == 30
    assert times[:2] == pytest.approx([1.0, 1.1])
    assert times[10] == pytest.approx(3.0)
    freeze = parse_item(item(1, "freeze_frame", 0.2, 0.6))
    faces = subject_faces(base, 10, [freeze])
    expected = PlanFaces(plan)
    assert edges(faces[1]) == pytest.approx(edges(expected.at(1.1)))
    assert faces[2:6] == [faces[2]] * 4
    assert edges(faces[2]) == pytest.approx(edges(expected.at(1.2)))
    assert edges(faces[6]) == pytest.approx(edges(expected.at(1.6)))
    assert edges(faces[10]) == pytest.approx(edges(expected.at(3.0)))


def test_slow_motion_frames_show_the_face_of_the_frame_they_play() -> None:
    plan = fill_plan()
    base = ProEditBase(Path("s.mp4"), 1.0, 5.0, plan, "fill")
    slowmo = parse_item(item(1, "slowmo", 1.0, 2.0, params={"speed": 0.5, "ramp_s": 0}))
    faces = subject_faces(base, 10, [slowmo])
    plain = subject_faces(base, 10)
    # Frame 10 + k plays frame 10 + k / 2 (the nearest, rounded half to even).
    assert faces[10:20] == [plain[round(10 + k / 2)] for k in range(10)]
    assert faces[:10] == plain[:10] and faces[20:] == plain[20:]
    assert faces[19] != plain[19]


def test_only_the_fill_layout_knows_the_face() -> None:
    plan = fill_plan()
    split = ProEditBase(Path("s.mp4"), 1.0, 5.0, plan, "split")
    assert subject_faces(split, 10) == [None] * 40
    scenes = (ScenePart(1.0, 2.0, plan, "fill"), ScenePart(2.0, 5.0, plan, "split"))
    framed = ProEditBase(Path("s.mp4"), 1.0, 5.0, plan, "split", scenes=scenes)
    faces = subject_faces(framed, 10)
    assert edges(faces[5]) == pytest.approx(edges(PlanFaces(plan).at(1.5)))
    assert faces[10:] == [None] * 30


def test_a_canvas_has_no_face_past_its_frames() -> None:
    canvas = Canvas(30, (540, 960), [Box(0.1, 0.1, 0.2, 0.2)])
    assert canvas.face(0) == Box(0.1, 0.1, 0.2, 0.2)
    assert canvas.face(1) is None and canvas.face(-1) is None


def object_plan() -> CropPlan:
    """fill_plan whose last keyframe saw an object in the window."""
    keyframes = [
        CropKeyframe(t=1.0, x=400, faces=[face(500, 0)]),
        CropKeyframe(t=4.0, x=500, faces=[face(550, 0), face(650, 1, False, "object")]),
    ]
    return fill_plan().model_copy(update={"keyframes": keyframes})


def test_the_tracked_object_is_found_like_the_face() -> None:
    objects = PlanFaces(object_plan(), tracked_object)
    assert edges(objects.at(4.0)) == pytest.approx(box(650, 500))
    assert objects.at(1.0) is None


def test_a_canvas_knows_what_its_overlays_are_anchored_to() -> None:
    base = ProEditBase(Path("s.mp4"), 1.0, 5.0, object_plan(), "fill")

    def overlay(anchor: str) -> list[TypedEdlItem]:
        params = {"asset": "circle", "anchor": anchor}
        zoom = item(2, "zoom_punch", 0.5, 1.0, params={"scale": 1.2})
        return [
            parse_item(item(1, "overlay", 0.0, 1.0, params=params)),
            parse_item(zoom),
        ]

    screen = canvas_of(base, overlay("screen"), (540, 960), 10)
    assert screen.objects == () and screen.cameras == {}
    face = canvas_of(base, overlay("face"), (540, 960), 10)
    assert face.faces == tuple(subject_faces(base, 10)) and face.objects == ()
    assert 7 in face.cameras and face.cameras[7].scale > 1
    tracked = canvas_of(base, overlay("object")[:1], (540, 960), 10)
    assert tracked.faces == () and tracked.cameras == {}
    assert tracked.objects == tuple(subject_faces(base, 10, pick=tracked_object))
    assert any(tracked.objects)
