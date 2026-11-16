"""Tests of a clip's scenes: splitting it at scene cuts and keeping the
scenes on the clip (pipeline/scenes), their crop plans
(pipeline/scene_framing) and their filter graph (pipeline/scene_graph)."""

from pathlib import Path

from builders import make_clip, plan_at, source_meta
from clipforge.models import CropPoint, SceneReframe, SignalList
from clipforge.pipeline.layout_parts import crop_window
from clipforge.pipeline.reframe import crop_path
from clipforge.pipeline.render_graph import clip_graph
from clipforge.pipeline.scene_framing import keyframed_plan, scene_parts, window_center
from clipforge.pipeline.scene_graph import ScenePart, scene_graph
from clipforge.pipeline.scenes import (
    default_scenes,
    fit_scenes,
    scene_problems,
    snap_scenes,
)
from clipforge.pipeline.step import META, SIGNALS, write_json

FRAME = (1280, 720)


def spans(scenes: list[SceneReframe]) -> list[tuple[float, float]]:
    return [(scene.start, scene.end) for scene in scenes]


def fixed(
    start: float, end: float, *points: CropPoint, **fields: object
) -> SceneReframe:
    return SceneReframe.model_validate(
        {"start": start, "end": end, "mode": "fixed", "crop_keyframes": points} | fields
    )


def test_default_scenes_split_at_the_cuts_at_least_half_a_second_apart() -> None:
    cuts = [40.0, 10.2, 12.0, 12.4, 15.0, 19.7, 3.0]

    scenes = default_scenes(10.0, 20.0, cuts, "fit")

    # 10.2 is too close to the start, 12.4 to 12.0 and 19.7 to the end.
    assert spans(scenes) == [(10.0, 12.0), (12.0, 15.0), (15.0, 20.0)]
    assert {(scene.mode, scene.layout) for scene in scenes} == {("auto", "fit")}
    assert spans(default_scenes(10.0, 20.0, [], "fill")) == [(10.0, 20.0)]


def test_scene_problems_need_scenes_that_cover_the_clip_in_order() -> None:
    good = [fixed(10, 12), fixed(12.0005, 15)]

    assert scene_problems([], 10, 15) == []
    assert scene_problems(good, 10, 15) == []
    assert len(scene_problems([fixed(10, 12), fixed(12.5, 15)], 10, 15)) == 1
    assert len(scene_problems([fixed(11, 12), fixed(12, 14)], 10, 15)) == 2
    snapped = snap_scenes(good, 10.0004, 14.9999)
    assert spans(snapped) == [(10.0004, 12.0), (12.0, 14.9999)]


def test_fit_scenes_follow_a_trim_and_an_extension_of_the_clip() -> None:
    scenes = [fixed(10, 12), fixed(12, 15), fixed(15, 20)]

    assert spans(fit_scenes(scenes, 13, 16)) == [(13, 15), (15, 16)]
    assert spans(fit_scenes(scenes, 8, 22)) == [(8, 12), (12, 15), (15, 22)]
    assert spans(fit_scenes(scenes, 12.5, 14)) == [(12.5, 14)]
    assert fit_scenes(scenes, 30, 40) == []


def test_a_fixed_scene_puts_its_window_at_its_keyframes_exactly() -> None:
    base = plan_at(400, 400, 400)
    scene = fixed(
        10.0,
        12.0,
        CropPoint(t=10.0, x=0.25, y=0.5),
        CropPoint(t=11.0, x=0.75, y=0.25),
        scale=0.5,
    )

    plan = keyframed_plan(base, base, scene, FRAME)

    assert (plan.width, plan.height) == (202, 360)
    # Centers 320 and 960 (x), 360 and 180 (y), less half the window.
    assert [(k.t, k.x, k.y) for k in plan.keyframes] == [
        (10.0, 218, 180),
        (11.0, 858, 0),
    ]
    # Linear from keyframe to keyframe, held after the last.
    crop = crop_window(plan, None, 10.0)
    assert "x='(218)+(+640*clip((t+0.000)/1.000,0,1))'" in crop
    assert "y='(180)+(-180*clip((t+0.000)/1.000,0,1))'" in crop


def test_a_fixed_scene_without_keyframes_holds_the_window_of_its_start() -> None:
    framed = plan_at(100, 300, 500)

    plan = keyframed_plan(framed, framed, fixed(10.5, 12.0), FRAME)

    assert window_center(framed, 10.5, 1280) == (402.0, 360.0)
    assert [(k.t, k.x, k.y) for k in plan.keyframes] == [(10.5, 200, 0)]
    assert plan.width == 404


def test_scenes_framed_alike_are_one_part(tmp_path: Path) -> None:
    write_json(tmp_path / META, source_meta())
    write_json(tmp_path / SIGNALS, SignalList([]))
    write_json(crop_path(tmp_path, 7), plan_at(400, 400))
    framed = plan_at(400, 400)
    scenes = [
        SceneReframe(start=10, end=10.5),
        SceneReframe(start=10.5, end=11, layout="fill", mode="auto"),
        SceneReframe(start=11, end=11.5, layout="fit", mode="fixed"),
        SceneReframe(start=11.5, end=12, layout="fit"),
        fixed(12, 12.5, CropPoint(t=12, x=0, y=0.5)),
    ]
    clip = make_clip("karaoke_bold", scene_reframes=scenes)

    parts = scene_parts(tmp_path, clip, framed)

    assert [(p.start, p.end, p.layout) for p in parts] == [
        (10, 11, "fill"),
        (11, 12, "fit"),
        (12, 12.5, "fill"),
    ]
    assert parts[0].plan is framed
    assert [(k.x, k.y) for k in parts[2].plan.keyframes] == [(0, 0)]
    assert scene_parts(tmp_path, make_clip("karaoke_bold"), framed) == []


def test_the_scene_graph_trims_frames_each_part_and_joins_them() -> None:
    plan = plan_at(400, 400)
    parts = [
        ScenePart(10.0, 11.0, plan, "fill"),
        ScenePart(11.0, 12.5, plan, "fit"),
        ScenePart(12.5, 14.0, plan, "split"),
    ]

    graph = scene_graph(parts, 10.0, (216, 384), 30, out="[framed]")

    chains = graph.split(";")
    assert chains[0] == "[0:V:0]fps=30,split=3[scene0][scene1][scene2]"
    assert chains[1].startswith("[scene0]trim=end=1.000000,setpts=PTS-STARTPTS,crop=")
    assert chains[1].endswith("[framed0]")
    assert chains[2].startswith(
        "[scene1]trim=start=1.000000:end=2.500000,setpts=PTS-STARTPTS,split=2"
        "[front1][back1]"
    )
    assert "[scene2]trim=start=2.500000,setpts=PTS-STARTPTS,split=2[upper2]" in graph
    assert chains[-1] == "[framed0][framed1][framed2]concat=n=3:v=1:a=0[framed]"


def test_one_scene_frames_the_clip_in_its_layout_without_a_concat() -> None:
    plan = plan_at(400, 400)

    graph = clip_graph(
        plan, "fill", 10.0, (216, 384), 30, scenes=[ScenePart(10, 12, plan, "fit")]
    )

    assert "boxblur" in graph
    assert "concat" not in graph
