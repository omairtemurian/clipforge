"""ensure_crop_plan: a clip made after processing is reframed before its
render; one that has a crop plan is left as it is."""

from pathlib import Path
from typing import Any

import pytest
from clipforge import clip_crop
from clipforge.clip_crop import ensure_crop_plan
from clipforge.db import ProjectRow
from clipforge.models import ProcessingSettings
from clipforge.pipeline.reframe import ClipSpan, crop_path
from seed import add_clip, add_plan, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Record the reframes and layout updates instead of running them."""
    seen: dict[str, list[Any]] = {"reframe": [], "layouts": []}

    def reframe(work: Path, clips: list[ClipSpan], aspect: str, **kw: Any) -> None:
        seen["reframe"].append((work, clips, aspect, kw))

    def layouts(engine: Engine, work: Path, ids: list[int], *rest: Any) -> None:
        seen["layouts"].append((ids, rest))

    monkeypatch.setattr(clip_crop, "reframe_clips", reframe)
    monkeypatch.setattr(clip_crop, "set_planned_layouts", layouts)
    return seen


def test_a_clip_without_a_crop_plan_is_reframed_as_its_project_says(
    engine: Engine, sample_mp4: Path, calls: dict[str, list[Any]]
) -> None:
    project_id = add_project(engine)
    with Session(engine) as session:
        project = session.get_one(ProjectRow, project_id)
        project.settings = ProcessingSettings(
            aspect="1:1",
            reframe_preset="vlog",
            default_layout="fill",
            camera_motion="normal",
        )
        session.add(project)
        session.commit()
    work = add_work(engine, project_id, sample_mp4)
    clip_id = add_clip(engine, project_id, "candidate", 0)

    assert ensure_crop_plan(engine, clip_id, work) is True

    [(where, spans, aspect, kw)] = calls["reframe"]
    assert (where, spans, aspect) == (work, [ClipSpan(clip_id, 10.0, 12.5)], "1:1")
    assert kw == {"preset": "vlog", "camera_motion": "normal"}
    assert calls["layouts"] == [([clip_id], ("fill", "balanced"))]


def test_a_clip_with_a_crop_plan_is_left_as_it_is(
    engine: Engine, sample_mp4: Path, calls: dict[str, list[Any]]
) -> None:
    project_id = add_project(engine)
    work = add_work(engine, project_id, sample_mp4)
    clip_id = add_clip(engine, project_id, "candidate", 0)
    add_plan(work, clip_id)

    assert ensure_crop_plan(engine, clip_id, work) is False
    assert calls == {"reframe": [], "layouts": []}
    assert crop_path(work, clip_id).is_file()
