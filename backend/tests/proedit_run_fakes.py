"""Helpers of the Pro Edit run tests (tests only): a clip whose project is
processed (source, transcript, signals, crop plan), an LLM that is offline,
no face models, and a stored plan."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from builders import FIXTURE_LAUGHS, cut, event
from clipforge.db import ClipRow
from clipforge.llm_http import LLMError
from clipforge.models import Clip, EdlItem, ProEditPlan, SignalList
from clipforge.pipeline.detectors import DetectFaces
from clipforge.pipeline.step import SIGNALS, write_json
from clipforge.proedit import signals
from clipforge.proedit.plan_store import save_plan
from seed import add_clip, add_plan, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


class OfflineLLM:
    """An LLM client whose every call fails, so the rule-based Director
    plans; it cannot send images, so the critic does not run."""

    provider = "offline"

    def complete_json(self, system: str, user: str) -> str:
        """Fail like a provider that cannot be reached."""
        raise LLMError("the LLM is offline")


@dataclass
class Processed:
    """A processed project: its id, work directory and original clip."""

    project_id: int
    work: Path
    clip_id: int


def processed_clip(engine: Engine, source: Path) -> Processed:
    """Add a project processed from source with the original clip 10-12.5 s
    "Pizza night", its crop plan and the signals the Pro Edit reads."""
    project_id = add_project(engine)
    work = add_work(engine, project_id, source)
    clip_id = add_clip(engine, project_id, "rendered", 80, "Pizza night")
    add_plan(work, clip_id)
    events = [*FIXTURE_LAUGHS, event("energy_peak", 11.0, 11.5, 0.9), cut(11.2)]
    write_json(work / SIGNALS, SignalList(events))
    return Processed(project_id, work, clip_id)


def no_face_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the signals see no faces instead of loading the face models."""

    @contextmanager
    def detector(_cfg: object) -> Iterator[DetectFaces]:
        yield lambda _frame: []

    monkeypatch.setattr(signals, "lazy_detector", detector)


def zoom(id: int, t_start: float, scale: float = 1.2) -> EdlItem:
    """A zoom punch item of 0.3 s at t_start."""
    return EdlItem(
        id=id,
        kind="zoom_punch",
        t_start=t_start,
        t_end=t_start + 0.3,
        params={"scale": scale},
        reason="the punchline",
    )


def store_plan(engine: Engine, clip_id: int, *items: EdlItem) -> ProEditPlan:
    """Store a rule-based clean_pro plan of clip clip_id with items as its
    next version."""
    plan = ProEditPlan(
        id=1,
        clip_id=clip_id,
        preset="clean_pro",
        intensity="standard",
        version=1,
        items=list(items),
        created_by="rule_director",
    )
    with Session(engine) as session:
        return save_plan(session, plan)


def clip_of(engine: Engine, clip_id: int) -> Clip:
    """Return clip clip_id as it is stored."""
    with Session(engine) as session:
        return session.get_one(ClipRow, clip_id).to_model()
