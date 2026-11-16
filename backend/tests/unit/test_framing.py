"""Tests of framing (pipeline/framing): the editor's aspect, fit background
and crop tool on top of a clip's crop plan."""

from pathlib import Path

import pytest
from builders import make_clip, plan_at, source_meta
from clipforge.models import (
    CropPlan,
    CropPoint,
    FaceBox,
    FrameBox,
    Framing,
    SignalList,
)
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.framing import (
    apply_crop_tool,
    crop_track,
    framed_plan,
    interpolate,
    uses_crop_tool,
)
from clipforge.pipeline.layout_parts import crop_window
from clipforge.pipeline.reframe import ClipSpan, crop_path, plan_crop, replan
from clipforge.pipeline.step import META, SIGNALS, StepError, write_json

FRAME = (1280, 720)


def point(t: float, x: float, y: float = 0.5) -> CropPoint:
    return CropPoint(t=t, x=x, y=y)


def lefts(plan: CropPlan) -> list[int]:
    return [keyframe.x for keyframe in plan.keyframes]


def tops(plan: CropPlan) -> list[int | None]:
    return [keyframe.y for keyframe in plan.keyframes]


def test_interpolate_is_linear_between_values_and_holds_outside() -> None:
    times, values = [10.0, 12.0], [100.0, 200.0]

    assert interpolate(times, values, 9.0) == 100.0
    assert interpolate(times, values, 11.0) == 150.0
    assert interpolate(times, values, 13.0) == 200.0
    assert interpolate([], [], 11.0) == 0.0


def test_a_default_framing_keeps_the_plan() -> None:
    plan = plan_at(400, 400)

    assert not uses_crop_tool(Framing())
    assert apply_crop_tool(plan, Framing(), FRAME) is plan
    assert uses_crop_tool(Framing(tracker=False))
    assert uses_crop_tool(Framing(scale=0.5))


def test_with_the_tracker_on_the_window_is_at_each_point_and_follows_between() -> None:
    plan = plan_at(300, 400, 500)
    # Tracked centers 502, 602, 702; the points put the center at 640 at
    # 10 s and at 12 s, so the shift is 138 then -62 (38 at 11 s).
    framing = Framing(points=[point(10.0, 0.5), point(12.0, 0.5)])

    framed = apply_crop_tool(plan, framing, FRAME)

    assert lefts(framed) == [438, 438, 438]
    assert (framed.width, framed.height) == (404, 720)
    assert tops(framed) == [0, 0, 0]


def test_one_point_with_the_tracker_on_shifts_the_whole_path() -> None:
    plan = plan_at(300, 400, 500)

    framed = apply_crop_tool(plan, Framing(points=[point(11.0, 0.5)]), FRAME)

    assert lefts(framed) == [338, 438, 538]


def test_with_the_tracker_off_the_window_stays_where_the_points_put_it() -> None:
    plan = plan_at(300, 400, 500)
    moving = Framing(tracker=False, points=[point(10.0, 0.25), point(12.0, 0.75)])

    assert lefts(apply_crop_tool(plan, moving, FRAME)) == [118, 438, 758]
    # Without points it holds the planned window of the first keyframe.
    assert lefts(apply_crop_tool(plan, Framing(tracker=False), FRAME)) == [300] * 3


def test_a_smaller_window_keeps_the_shape_and_sits_at_the_point() -> None:
    plan = plan_at(400, 400)
    framing = Framing(scale=0.5, points=[point(10.0, 0.25, 0.25)])

    framed = apply_crop_tool(plan, framing, FRAME)

    assert (framed.width, framed.height) == (202, 360)
    # Center (320, 180): left 219 rounded down to even, top 0.
    assert lefts(framed) == [218, 218]
    assert tops(framed) == [0, 0]
    assert framed.split == plan.split


def test_the_window_stays_inside_the_frame() -> None:
    plan = plan_at(400, 400)
    corner = Framing(scale=0.5, tracker=False, points=[point(10.0, 1.0, 1.0)])
    origin = Framing(scale=0.5, tracker=False, points=[point(10.0, 0.0, 0.0)])

    at_corner = apply_crop_tool(plan, corner, FRAME)
    at_origin = apply_crop_tool(plan, origin, FRAME)

    assert (lefts(at_corner), tops(at_corner)) == ([1078, 1078], [360, 360])
    assert (lefts(at_origin), tops(at_origin)) == ([0, 0], [0, 0])


def test_the_crop_filter_moves_the_top_of_a_crop_tool_window() -> None:
    plan = plan_at(400, 400)
    framing = Framing(
        scale=0.5,
        tracker=False,
        points=[point(10.0, 0.5, 0.25), point(11.0, 0.5, 0.75)],
    )

    framed = apply_crop_tool(plan, framing, FRAME)

    assert tops(framed) == [0, 360]
    assert crop_window(framed, None, 10.0) == (
        "crop=w=202:h=360:x='538':y='(0)+(+360*clip((t+0.000)/1.000,0,1))'"
    )
    assert crop_window(plan, None, 10.0).endswith(":y=0")


def faces_at(x: float) -> list[FaceBox]:
    return [FaceBox(x=x, y=200.0, width=100.0, height=100.0, score=0.9)]


def test_replan_frames_the_faces_of_the_plan_for_another_aspect() -> None:
    span = ClipSpan(7, 10.0, 11.0)
    faces = [faces_at(800.0) for _ in sample_times(span.start, span.end)]
    plan = plan_crop(span, "9:16", FRAME, faces, [])
    expected = plan_crop(span, "1:1", FRAME, faces, [])

    square = replan(plan, "1:1", FRAME, [])

    assert replan(plan, "9:16", FRAME, []) is plan
    assert square.model_dump(exclude={"created_at"}) == expected.model_dump(
        exclude={"created_at"}
    )
    assert (square.width, square.height) == (720, 720)


@pytest.fixture
def work(tmp_path: Path) -> Path:
    """A job directory with meta.json (1280x720), no signals and clip 7's
    crop plan."""
    write_json(tmp_path / META, source_meta())
    write_json(tmp_path / SIGNALS, SignalList([]))
    write_json(crop_path(tmp_path, 7), plan_at(400, 400))
    return tmp_path


def test_framed_plan_applies_aspect_offset_crop_tool_and_background(
    work: Path,
) -> None:
    plain = make_clip("karaoke_bold")
    framing = Framing(aspect="1:1", background="black", tracker=False)
    clip = make_clip("karaoke_bold", framing=framing)

    assert framed_plan(work, plain).model_dump(exclude={"created_at"}) == plan_at(
        400, 400
    ).model_dump(exclude={"created_at"})
    framed = framed_plan(work, clip)
    assert (framed.aspect, framed.width, framed.background) == ("1:1", 720, "black")
    nudged = framed_plan(work, make_clip("karaoke_bold", crop_offset=0.5))
    assert lefts(nudged) == [602, 602]


def test_framed_plan_needs_meta_only_for_the_crop_tool(work: Path) -> None:
    (work / META).unlink()

    assert framed_plan(work, make_clip("karaoke_bold")).width == 404
    with pytest.raises(StepError, match="meta.json"):
        framed_plan(work, make_clip("karaoke_bold", framing=Framing(scale=0.5)))


def test_crop_track_is_the_planned_window_in_an_aspect(work: Path) -> None:
    track = crop_track(work, 7, None)
    square = crop_track(work, 7, "1:1")

    assert (track.aspect, track.frame_width, track.frame_height) == ("9:16", 1280, 720)
    assert (track.width, track.height, track.y) == (404, 720, 0)
    assert (track.times, track.xs) == ([10.0, 11.0], [400, 400])
    assert (square.aspect, square.width, square.height) == ("1:1", 720, 720)


def test_crop_track_has_the_facecam_box_found_or_planned(work: Path) -> None:
    assert crop_track(work, 7, None).facecam is None
    face = FaceBox(x=1000.0, y=200.0, width=100.0, height=100.0, score=0.9)
    plan = plan_at(400, 400)
    for keyframe in plan.keyframes:
        keyframe.faces = [face]
    write_json(crop_path(work, 7), plan)

    # A 3x face-height square (300 px) around the face's center (1050, 250).
    found = crop_track(work, 7, None).facecam
    assert found == FrameBox(
        x=900 / 1280, y=100 / 720, width=300 / 1280, height=300 / 720
    )

    planned = FrameBox(x=0.1, y=0.2, width=0.3, height=0.4)
    write_json(crop_path(work, 7), plan.model_copy(update={"facecam": planned}))
    assert crop_track(work, 7, None).facecam == planned
