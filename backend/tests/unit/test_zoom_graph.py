"""Unit tests of auto zoom's filters (pipeline/zoom_graph): the subject that
a punch-in centers on and the scale and crop expressions, and where
render_graph puts them."""

import math
import re
from pathlib import Path

from clipforge.models import CropKeyframe, CropPlan, FaceBox, ZoomKeyframe
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.layouts import layout_graph
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render_graph import clip_graph, cut_graph, subtitles_filter
from clipforge.pipeline.zoom_graph import subject_center, zoom_filter

SIZE = (1080, 1920)
PLAN = plan_crop(
    ClipSpan(1, 10.0, 12.0), "9:16", (1280, 720), [[] for _ in sample_times(10, 12)], []
)
ZOOM = [
    ZoomKeyframe(t=10.5, scale=1.0),
    ZoomKeyframe(t=10.7, scale=1.15),
    ZoomKeyframe(t=11.5, scale=1.15),
    ZoomKeyframe(t=12.0, scale=1.0),
]


def face(center_x: float, center_y: float) -> FaceBox:
    """Return a 100 px face centered at (center_x, center_y)."""
    return FaceBox(x=center_x - 50, y=center_y - 50, width=100, height=100, score=0.9)


def faced_plan() -> CropPlan:
    """Return a 404x720 fill plan with keyframes at 10.0 s (x 400, a face at
    (500, 180)), 10.2 s (x 440, y 20, a face at (900, 380) beyond the
    window's right edge) and 10.4 s (x 440, no face)."""
    keyframes = [
        CropKeyframe(t=10.0, x=400, faces=[face(500, 180), face(700, 400)]),
        CropKeyframe(t=10.2, x=440, y=20, faces=[face(900, 380)]),
        CropKeyframe(t=10.4, x=440, faces=[]),
    ]
    return PLAN.model_copy(
        update={"width": 404, "height": 720, "y": 0, "keyframes": keyframes}
    )


def test_subject_center_is_the_largest_face_of_the_nearest_keyframe() -> None:
    plan = faced_plan()

    assert subject_center(plan, "fill", 9.0) == (100 / 404, 0.25)
    assert subject_center(plan, "fill", 10.09) == (100 / 404, 0.25)
    # The face beyond the window's edge clamps to it; y is the keyframe's.
    assert subject_center(plan, "fill", 10.11) == (1.0, 360 / 720)
    assert subject_center(plan, "fill", 10.4) == (0.5, 0.5)
    assert subject_center(plan, "fit", 10.0) == (0.5, 0.5)
    assert subject_center(plan, "split", 10.0) == (0.5, 0.5)
    assert subject_center(PLAN.model_copy(update={"keyframes": []}), "fill", 10.0) == (
        0.5,
        0.5,
    )


def test_subject_center_is_the_face_marked_subject_when_there_is_one() -> None:
    plan = faced_plan()
    (first, *_) = plan.keyframes
    speaker = first.faces[1].model_copy(update={"subject": True})
    marked = first.model_copy(update={"faces": [first.faces[0], speaker]})
    plan = plan.model_copy(update={"keyframes": [marked, *plan.keyframes[1:]]})

    # The speaker at (700, 400) rather than the largest face at (500, 180).
    assert subject_center(plan, "fill", 10.0) == (300 / 404, 400 / 720)


def test_zoom_filter_scales_each_frame_and_crops_around_the_subject() -> None:
    scale = (
        "(1.0000)+((+0.1500*clip((t-0.500)/0.200,0,1))+"
        "(-0.1500*clip((t-1.500)/0.500,0,1)))"
    )
    width = f"max(1080,2*trunc(1080*({scale})/2))"
    height = f"max(1920,2*trunc(1920*({scale})/2))"

    assert zoom_filter(ZOOM, PLAN, "fit", 10.0, SIZE) == (
        f"scale=w='{width}':h='{height}':eval=frame,crop=w=1080:h=1920:"
        f"x='clip(trunc((540.0)*{width}/1080-540),0,{width}-1080)':"
        f"y='clip(trunc((960.0)*{height}/1920-960),0,{height}-1920)',setsar=1"
    )


def test_zoom_filter_moves_the_center_with_the_subject() -> None:
    zoom = [ZoomKeyframe(t=10.0, scale=1.1), ZoomKeyframe(t=10.4, scale=1.1)]

    graph = zoom_filter(zoom, faced_plan(), "fill", 10.0, SIZE)

    # x 1080 * 100 / 404 = 267.3 at 10.0 s, then the frame's center.
    assert "x='clip(trunc(((267.3)+(+272.7*clip((t+0.000)/0.400,0,1)))*" in graph
    assert "y='clip(trunc(((480.0)+(+480.0*clip((t+0.000)/0.400,0,1)))*" in graph


def test_zoom_filter_without_zoom_is_empty() -> None:
    assert zoom_filter([], PLAN, "fill", 10.0, SIZE) == ""
    flat = [ZoomKeyframe(t=10.0, scale=1.0), ZoomKeyframe(t=11.0, scale=1.0)]
    assert zoom_filter(flat, PLAN, "fill", 10.0, SIZE) == ""
    assert clip_graph(PLAN, "fill", 10.0, SIZE, 30, zoom=flat) == layout_graph(
        PLAN, "fill", 10.0, SIZE, 30
    )


def test_clip_graph_zooms_the_framed_clip_before_its_cuts_and_captions(
    tmp_path: Path,
) -> None:
    captions = tmp_path / "1.ass"
    spans = [(0.0, 1.0), (1.5, 2.0)]
    unzoomed = layout_graph(PLAN, "fill", 10.0, SIZE, 30, out="[unzoomed]")
    zoomed = f"[unzoomed]{zoom_filter(ZOOM, PLAN, 'fill', 10.0, SIZE)}"

    graph = clip_graph(PLAN, "fill", 10.0, SIZE, 30, captions, spans=spans, zoom=ZOOM)

    assert graph == (
        f"{unzoomed};{zoomed}[framed];"
        f"{cut_graph(spans, ('[0:a:0]', '[a]'), ('[framed]', '[cut]'))};"
        f"[cut]{subtitles_filter(captions)}[v]"
    )
    assert (
        clip_graph(PLAN, "fill", 10.0, SIZE, 30, zoom=ZOOM) == f"{unzoomed};{zoomed}[v]"
    )


def scaled_sizes(graph: str, times: list[float]) -> set[tuple[int, int]]:
    """The (w, h) that the scale of zoom_filter's graph gives the frames at
    times, evaluated as ffmpeg does (doubles; clip, trunc and max)."""
    width, height = re.findall(r"scale=w='([^']*)':h='([^']*)'", graph)[0]
    names = {
        "clip": lambda v, lo, hi: min(max(v, lo), hi),
        "trunc": math.trunc,
        "max": max,
    }
    return {
        (eval(width, {**names, "t": t}), eval(height, {**names, "t": t}))  # noqa: S307
        for t in times
    }


def test_a_zoom_back_to_1_never_scales_below_the_frame() -> None:
    # Summed as (1 + 0.15) + (-0.15 + 0.12 * ramp), the scale between the
    # zoom back and the next punch is 0.9999999999999999 in doubles: without
    # the floor those frames were 1078x1918, cropped at 1080x1920 (TASK-236).
    zoom = [
        ZoomKeyframe(t=10.0, scale=1.0),
        ZoomKeyframe(t=10.2, scale=1.15),
        ZoomKeyframe(t=10.8, scale=1.15),
        ZoomKeyframe(t=11.3, scale=1.0),
        ZoomKeyframe(t=11.6, scale=1.0),
        ZoomKeyframe(t=11.8, scale=1.12),
    ]
    assert (1.0 + 0.15) + (-0.15 + 0.0) < 1.0
    graph = zoom_filter(zoom, PLAN, "fill", 10.0, SIZE)

    between = scaled_sizes(graph, [1.3, 1.45, 1.59])
    during = scaled_sizes(graph, [x / 30 for x in range(0, 60)])

    assert between == {SIZE}
    assert min(w for w, _ in during) == 1080 and min(h for _, h in during) == 1920
    assert (1242, 2208) in during
