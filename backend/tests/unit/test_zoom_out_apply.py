"""Tests of planning a project's zoom-out moments again
(clipforge/zoom_out_apply): clips without manual scenes are, the others keep
their framing."""

from pathlib import Path

from clipforge.clip_edit import apply_patch
from clipforge.db import ClipRow
from clipforge.models import ClipPatch, SceneReframe
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import crop_path, plan_crop
from clipforge.pipeline.step import write_json
from clipforge.zoom_out_apply import reapply_zoom_out
from sqlalchemy import Engine
from sqlmodel import Session
from test_clip_layouts import CUT, face, reframed_clip, stored


def spread_plan(engine: Engine, work: Path) -> tuple[int, int]:
    """Save a clip whose faces spread wide from 5 to 9 s, with its plan in
    work; return the clip's id and its project's."""
    clip_id, clip = reframed_clip(engine, work)
    faces = [
        [face(213), face(1067)] if 5 <= t < 9 else [face(640)]
        for t in sample_times(clip.start, clip.end)
    ]
    plan = plan_crop(clip, "9:16", (1280, 720), faces, [CUT])
    write_json(crop_path(work, clip_id), plan)
    return clip_id, stored(engine, clip_id).project_id


def zoomed(engine: Engine, clip_id: int) -> list[str]:
    return [scene.layout for scene in stored(engine, clip_id).scene_reframes]


def test_a_clip_without_manual_scenes_is_planned_again(
    engine: Engine, tmp_path: Path
) -> None:
    clip_id, project_id = spread_plan(engine, tmp_path)

    planned = reapply_zoom_out(engine, tmp_path, project_id, "auto", "balanced")

    assert list(planned) == [clip_id]
    assert zoomed(engine, clip_id) == ["fill", "fit", "fill"]

    planned = reapply_zoom_out(engine, tmp_path, project_id, "auto", "off")

    assert list(planned) == [clip_id]
    row = stored(engine, clip_id)
    assert (row.layout, row.scene_reframes) == ("fill", [])


def test_a_clip_with_manual_scenes_keeps_them(engine: Engine, tmp_path: Path) -> None:
    clip_id, project_id = spread_plan(engine, tmp_path)
    clip = stored(engine, clip_id).to_model()
    scenes = [
        SceneReframe(start=clip.start, end=CUT, layout="fill", mode="fixed"),
        SceneReframe(start=CUT, end=clip.end, layout="fill"),
    ]
    with Session(engine) as session:
        apply_patch(
            session,
            session.get_one(ClipRow, clip_id),
            ClipPatch(scene_reframes=scenes),
            60.0,
        )

    planned = reapply_zoom_out(engine, tmp_path, project_id, "auto", "frequent")

    assert list(planned) == []
    assert stored(engine, clip_id).scene_reframes == scenes


def test_a_clip_in_a_layout_of_the_owners_choice_is_left_alone(
    engine: Engine, tmp_path: Path
) -> None:
    clip_id, project_id = spread_plan(engine, tmp_path)
    with Session(engine) as session:
        row = session.get_one(ClipRow, clip_id)
        row.layout = "grid"
        session.add(row)
        session.commit()

    planned = reapply_zoom_out(engine, tmp_path, project_id, "auto", "balanced")

    assert list(planned) == []
    assert stored(engine, clip_id).layout == "grid"


def test_nothing_changes_when_every_clip_has_a_layout_chosen(
    engine: Engine, tmp_path: Path
) -> None:
    clip_id, project_id = spread_plan(engine, tmp_path)

    assert (
        list(reapply_zoom_out(engine, tmp_path, project_id, "grid", "balanced")) == []
    )
    assert stored(engine, clip_id).scene_reframes == []


def test_a_clip_without_a_plan_is_skipped(engine: Engine, tmp_path: Path) -> None:
    clip_id, project_id = spread_plan(engine, tmp_path)
    crop_path(tmp_path, clip_id).unlink()

    assert (
        list(reapply_zoom_out(engine, tmp_path, project_id, "auto", "balanced")) == []
    )
