"""Tests of the facecam box of the screenshare and gameplay layouts
(SPEC-v2 3.3): found from the subject's face (layout_windows.facecam_box)
or drawn by the user (Framing.facecam), and how framing puts it in the
plan that render uses."""

from pathlib import Path

import pytest
from builders import make_clip, source_meta
from clipforge.models import FaceBox, FrameBox, Framing, SceneReframe
from clipforge.pipeline.framing import framed_plan
from clipforge.pipeline.layout_windows import facecam_box, subject_faces
from clipforge.pipeline.reframe import ClipSpan, crop_path, plan_crop
from clipforge.pipeline.step import META, StepError, write_json
from pydantic import ValidationError

FRAME = (1280, 720)
CLIP = ClipSpan(7, 10.0, 12.0)
DRAWN = FrameBox(x=0.75, y=0.5, width=0.25, height=0.5)


def face(
    center_x: float,
    center_y: float = 300.0,
    size: float = 100.0,
    kind: str = "face",
    subject: bool = False,
) -> FaceBox:
    """Return a size px face (or kind) centered at center_x, center_y."""
    half = size / 2
    return FaceBox.model_validate(
        {
            "x": center_x - half,
            "y": center_y - half,
            "width": size,
            "height": size,
            "score": 0.9,
            "kind": kind,
            "subject": subject,
        }
    )


def test_subject_faces_are_the_marked_face_or_else_the_largest() -> None:
    marked = face(1000, subject=True)
    big, person = face(200, size=200), face(640, size=400, kind="person")

    subjects = subject_faces([[big, marked], [big, face(900)], [person], []])

    assert subjects == [marked, big, None, None]


def test_the_facecam_box_is_a_square_around_the_median_face() -> None:
    faces = [[face(400, 300, 100)], [face(410, 310, 120)], [face(420, 320, 100)]]

    box = facecam_box(faces, FRAME)

    # 3x the median height (100) around the median center (410, 310).
    assert box == FrameBox(
        x=260 / 1280, y=160 / 720, width=300 / 1280, height=300 / 720
    )


def test_the_facecam_box_stays_inside_the_frame() -> None:
    corner = facecam_box([[face(1250, 700, 100)]], FRAME)
    huge = facecam_box([[face(640, 360, 400)]], FRAME)

    assert corner == FrameBox(
        x=980 / 1280, y=420 / 720, width=300 / 1280, height=300 / 720
    )
    # At most the frame's height: a 720 px square in the middle.
    assert huge == FrameBox(x=280 / 1280, y=0, width=720 / 1280, height=1)


def test_no_facecam_box_without_a_face() -> None:
    assert facecam_box([[face(640, kind="person")], []], FRAME) is None
    assert facecam_box([], FRAME) is None


def test_a_reframe_plan_holds_the_facecam_box() -> None:
    faces = [[face(1120, 560)] for _ in range(20)]

    plan = plan_crop(CLIP, "9:16", FRAME, faces, [])
    square = plan_crop(CLIP, "1:1", FRAME, faces, [])

    assert plan.facecam == facecam_box(faces, FRAME)
    assert square.facecam == plan.facecam


def test_a_frame_box_must_be_inside_the_frame_and_not_empty() -> None:
    with pytest.raises(ValidationError, match="inside the frame"):
        FrameBox(x=0.8, y=0.0, width=0.3, height=0.5)
    with pytest.raises(ValidationError):
        FrameBox(x=0.5, y=0.5, width=0.0, height=0.5)


@pytest.fixture
def work(tmp_path: Path) -> Path:
    """A job directory with meta.json (1280x720) and clip 7's crop plan with
    a face at (1120, 560), made before the facecam layouts (no box)."""
    write_json(tmp_path / META, source_meta())
    faces = [[face(1120, 560)] for _ in range(20)]
    plan = plan_crop(CLIP, "9:16", FRAME, faces, [])
    write_json(crop_path(tmp_path, 7), plan.model_copy(update={"facecam": None}))
    return tmp_path


def test_framing_finds_the_facecam_when_a_clip_or_scene_uses_one(
    work: Path,
) -> None:
    expected = facecam_box([[face(1120, 560)]], FRAME)
    scenes = [
        SceneReframe(start=10.0, end=11.0, layout="screenshare"),
        SceneReframe(start=11.0, end=12.5),
    ]

    plain = framed_plan(work, make_clip("karaoke_bold"))
    game = framed_plan(work, make_clip("karaoke_bold", layout="gameplay"))
    scened = framed_plan(work, make_clip("karaoke_bold", scene_reframes=scenes))

    assert plain.facecam is None
    assert game.facecam == expected and scened.facecam == expected


def test_the_drawn_facecam_replaces_the_found_one(work: Path) -> None:
    (work / META).unlink()
    framing = Framing(facecam=DRAWN)

    drawn = framed_plan(
        work, make_clip("karaoke_bold", layout="gameplay", framing=framing)
    )

    assert drawn.facecam == DRAWN


def test_finding_the_facecam_of_an_older_plan_needs_the_frame_size(
    work: Path,
) -> None:
    (work / META).unlink()

    with pytest.raises(StepError, match="meta"):
        framed_plan(work, make_clip("karaoke_bold", layout="screenshare"))
