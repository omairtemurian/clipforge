"""Tests of the layouts that new clips get from the project's default layout
(SPEC-v2 3.3, clipforge/clip_layouts): reframe's choice, one layout for
every clip, or a layout per segment (dynamic), whose scenes the editor can
change and that are then kept."""

from pathlib import Path

import pytest
from builders import source_meta
from clipforge.clip_edit import apply_patch
from clipforge.clip_layouts import set_planned_layouts
from clipforge.clips import save_clips
from clipforge.db import ClipRow
from clipforge.models import (
    CandidateList,
    ClipPatch,
    DefaultLayout,
    FaceBox,
    ProcessingSettings,
    SceneReframe,
    SignalEvent,
    SignalList,
)
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, crop_path, plan_crop
from clipforge.pipeline.step import META, SIGNALS, StepError, write_json
from fakes import LLM_RESPONSE
from pydantic import ValidationError
from seed import add_project
from sqlalchemy import Engine
from sqlmodel import Session
from test_clips import with_scores

_, A, *_ = CandidateList.model_validate_json(LLM_RESPONSE.read_bytes()).clips
SETTINGS = ProcessingSettings(auto_cut=False, auto_zoom=False)
CUT = 12.0


def face(center_x: float) -> FaceBox:
    """Return a 100 px face centered at center_x, 360."""
    return FaceBox(x=center_x - 50, y=310, width=100, height=100, score=0.9)


def reframed_clip(engine: Engine, work: Path) -> tuple[int, ClipSpan]:
    """Save clip A (0.5-35.2 s) and write the job files of work: its crop
    plan (one face up to the scene cut at CUT seconds, two after it),
    meta.json and signals.json; return its id and span."""
    (clip_id,) = save_clips(
        engine, add_project(engine), [with_scores(A, 80)], SETTINGS, work
    )
    clip = ClipSpan(clip_id, A.start, A.end)
    faces = [
        [face(640)] if t < CUT else [face(213), face(1067)]
        for t in sample_times(clip.start, clip.end)
    ]
    write_json(
        crop_path(work, clip_id), plan_crop(clip, "9:16", (1280, 720), faces, [CUT])
    )
    write_json(work / META, source_meta())
    signals = [SignalEvent(kind="scene_cut", start=CUT, end=CUT, intensity=1.0)]
    write_json(work / SIGNALS, SignalList(signals))
    return clip_id, clip


def stored(engine: Engine, clip_id: int) -> ClipRow:
    """Return the row of clip clip_id."""
    with Session(engine) as session:
        return session.get_one(ClipRow, clip_id)


def test_the_default_layout_is_auto_and_takes_any_layout() -> None:
    assert ProcessingSettings().default_layout == "auto"
    for value in ("dynamic", "grid", "screenshare"):
        assert ProcessingSettings(default_layout=value).default_layout == value
    with pytest.raises(ValidationError):
        ProcessingSettings(default_layout="mosaic")  # type: ignore[arg-type]


@pytest.mark.parametrize(("default", "layout"), [("auto", "split"), ("pip", "pip")])
def test_auto_takes_reframes_layout_and_a_layout_is_set_on_every_clip(
    engine: Engine, tmp_path: Path, default: DefaultLayout, layout: str
) -> None:
    clip_id, _ = reframed_clip(engine, tmp_path)

    set_planned_layouts(engine, tmp_path, [clip_id], default)

    row = stored(engine, clip_id)
    assert (row.layout, row.scene_reframes) == (layout, [])


def test_dynamic_gives_each_segment_its_layout(engine: Engine, tmp_path: Path) -> None:
    clip_id, clip = reframed_clip(engine, tmp_path)

    set_planned_layouts(engine, tmp_path, [clip_id], "dynamic")

    row = stored(engine, clip_id)
    assert row.layout == "split"
    assert [(s.start, s.end, s.layout) for s in row.scene_reframes] == [
        (clip.start, CUT, "fill"),
        (CUT, clip.end, "split"),
    ]


def test_a_manual_layout_per_segment_is_kept(engine: Engine, tmp_path: Path) -> None:
    clip_id, clip = reframed_clip(engine, tmp_path)
    set_planned_layouts(engine, tmp_path, [clip_id], "dynamic")
    scenes = [
        SceneReframe(start=clip.start, end=CUT, layout="pip"),
        SceneReframe(start=CUT, end=clip.end, layout="split"),
    ]

    with Session(engine) as session:
        row = session.get_one(ClipRow, clip_id)
        apply_patch(session, row, ClipPatch(scene_reframes=scenes), 60.0)
    set_planned_layouts(engine, tmp_path, [clip_id], "dynamic")

    assert stored(engine, clip_id).scene_reframes == scenes


def test_one_layout_throughout_stores_no_scenes(engine: Engine, tmp_path: Path) -> None:
    clip_id, clip = reframed_clip(engine, tmp_path)
    plan = plan_crop(
        clip, "9:16", (1280, 720), [[]] * len(sample_times(clip.start, clip.end)), []
    )
    write_json(crop_path(tmp_path, clip_id), plan)

    set_planned_layouts(engine, tmp_path, [clip_id], "dynamic")

    row = stored(engine, clip_id)
    assert (row.layout, row.scene_reframes) == ("fit", [])


def test_dynamic_needs_the_scene_cuts(engine: Engine, tmp_path: Path) -> None:
    clip_id, _ = reframed_clip(engine, tmp_path)
    (tmp_path / SIGNALS).unlink()

    with pytest.raises(StepError, match="signals"):
        set_planned_layouts(engine, tmp_path, [clip_id], "dynamic")
    set_planned_layouts(engine, tmp_path, [clip_id], "auto")


def test_auto_zooms_out_where_the_faces_spread_wider_than_the_fill(
    engine: Engine, tmp_path: Path
) -> None:
    clip_id, clip = reframed_clip(engine, tmp_path)
    faces = [
        [face(213), face(1067)] if 5 <= t < 9 else [face(640)]
        for t in sample_times(clip.start, clip.end)
    ]
    plan = plan_crop(clip, "9:16", (1280, 720), faces, [CUT])
    write_json(crop_path(tmp_path, clip_id), plan)

    set_planned_layouts(engine, tmp_path, [clip_id], "auto", "off")
    off = stored(engine, clip_id)
    assert (off.layout, off.scene_reframes) == ("fill", [])
    set_planned_layouts(engine, tmp_path, [clip_id], "auto", "balanced")

    row = stored(engine, clip_id)
    assert row.layout == "fill"
    assert [(s.start, s.end, s.layout) for s in row.scene_reframes] == [
        (clip.start, 5.0, "fill"),
        (5.0, 9.0, "fit"),
        (9.0, clip.end, "fill"),
    ]


def test_zoom_outs_are_not_planned_over_a_clips_scenes(
    engine: Engine, tmp_path: Path
) -> None:
    clip_id, clip = reframed_clip(engine, tmp_path)
    scenes = [
        SceneReframe(start=clip.start, end=CUT, layout="fill", mode="fixed"),
        SceneReframe(start=CUT, end=clip.end, layout="split"),
    ]
    with Session(engine) as session:
        row = session.get_one(ClipRow, clip_id)
        apply_patch(session, row, ClipPatch(scene_reframes=scenes), 60.0)

    set_planned_layouts(engine, tmp_path, [clip_id], "auto", "frequent")

    assert stored(engine, clip_id).scene_reframes == scenes
