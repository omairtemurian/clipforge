"""Auto headline and motion graphics endpoints (SPEC-v2 3.5): items of a
clip's text track in its project's brand style (clipforge.brand_style).

POST /clips/{id}/headline gives the clip a headline (pipeline/headline):
the text given, or a line the LLM writes; it becomes the clip's hook_text
and the text of its headline item (made in the brand style if it has none;
an edited one keeps its style and times). DELETE removes both.
POST /clips/{id}/motion-graphics has the LLM pick names, numbers, dates and
key phrases, placed on the words they go with (pipeline/motion_graphics),
replacing the clip's earlier motion graphics; DELETE removes them.

Each answers the clip: 404 if it does not exist, 409 while it renders or
if its transcript is missing, 422 if the text track has no room, 502 if the
LLM cannot be reached or sends nothing valid. A change stores a version
(undo). The rendered video is not changed: render the clip again.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import config, usage
from clipforge.api.deps import clip_row, get_engine, get_llm, work_dir
from clipforge.api.errors import ApiError
from clipforge.brand_style import BrandStyle, brand_style
from clipforge.clip_graphics import (
    MotionGraphicsError,
    place_motion_graphics,
    project_brand,
    write_headline,
)
from clipforge.db import ClipRow
from clipforge.fonts import available_fonts
from clipforge.hook_theme import HookThemeError
from clipforge.llm import LLMClient
from clipforge.llm_http import LLMError
from clipforge.models import Clip, HeadlineApply, MotionGraphicsApply
from clipforge.pipeline.headline import with_headline, without_headline
from clipforge.pipeline.motion_graphics import text_room, without_motion_graphics
from clipforge.pipeline.step import StepError
from clipforge.timeline import clip_length, tidy_props, timeline_assets, track_problems

logger = logging.getLogger(__name__)

router = APIRouter()

RowChange = Callable[[ClipRow, Clip], None]


@router.post("/clips/{clip_id}/headline")
def apply_headline(
    clip_id: int,
    body: HeadlineApply,
    engine: Annotated[Engine, Depends(get_engine)],
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> Clip:
    """Give the clip the headline body.text, or one the LLM writes from its
    words when text is null (errors: see the module)."""
    clip, style, work = _clip_style(engine, clip_id, need_work=body.text is None)
    text = body.text
    if text is None:
        with _llm_errors(clip), usage.recording(engine, clip.project_id):
            text = write_headline(llm, work, clip)
    headline = text
    length = clip_length(clip, config.settings.render.fps)

    def change(row: ClipRow, current: Clip) -> None:
        """Set the headline of row, whose clip is current."""
        row.hook_text = headline
        text_items = with_headline(current.tracks.text, headline, style, length)
        row.tracks = current.tracks.model_copy(update={"text": text_items})

    return _save(engine, clip_id, change)


@router.delete("/clips/{clip_id}/headline")
def remove_headline(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Remove the clip's headline: its hook_text and its headline item."""

    def change(row: ClipRow, current: Clip) -> None:
        """Clear the headline of row, whose clip is current."""
        row.hook_text = ""
        text_items = without_headline(current.tracks.text)
        row.tracks = current.tracks.model_copy(update={"text": text_items})

    return _save(engine, clip_id, change)


@router.post("/clips/{clip_id}/motion-graphics")
def apply_motion_graphics(
    clip_id: int,
    body: MotionGraphicsApply,
    engine: Annotated[Engine, Depends(get_engine)],
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> Clip:
    """Replace the clip's motion graphics with at most body.max_items that
    the LLM picks (fewer if the text track's other items leave less room:
    422 if they leave none). A reply with no picks removes them."""
    clip, style, work = _clip_style(engine, clip_id, need_work=True)
    room = min(body.max_items, text_room(clip.tracks.text))
    if room == 0:
        raise ApiError(
            422,
            "validation_error",
            "the text track is full: remove a text overlay to make room",
        )
    fps = config.settings.render.fps
    with _llm_errors(clip), usage.recording(engine, clip.project_id):
        graphics = place_motion_graphics(llm, work, clip, style, room, fps)

    def change(row: ClipRow, current: Clip) -> None:
        """Put graphics on row's text track, whose clip is current."""
        text_items = without_motion_graphics(current.tracks.text) + graphics
        row.tracks = current.tracks.model_copy(update={"text": text_items})

    return _save(engine, clip_id, change)


@router.delete("/clips/{clip_id}/motion-graphics")
def remove_motion_graphics(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Remove the clip's motion graphics (its other text items stay)."""

    def change(row: ClipRow, current: Clip) -> None:
        """Take the motion graphics off row's text track."""
        text_items = without_motion_graphics(current.tracks.text)
        row.tracks = current.tracks.model_copy(update={"text": text_items})

    return _save(engine, clip_id, change)


def _clip_style(
    engine: Engine, clip_id: int, *, need_work: bool
) -> tuple[Clip, BrandStyle, Path]:
    """Return clip clip_id, its project's brand style and, if need_work,
    the work directory of its process job (409 if there is none; else an
    empty path)."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        style = brand_style(project_brand(session, clip.project_id), available_fonts())
        work = work_dir(session, clip.project_id) if need_work else Path()
    return clip, style, work


@contextmanager
def _llm_errors(clip: Clip) -> Iterator[None]:
    """Answer a missing transcript with 409, and an LLM that cannot be
    reached or sends nothing valid with 502."""
    try:
        yield
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    except (LLMError, HookThemeError, MotionGraphicsError) as exc:
        logger.warning("clip %d: no graphics from the LLM: %s", clip.id, exc)
        raise ApiError(502, "llm_error", str(exc)) from exc


def _save(engine: Engine, clip_id: int, change: RowChange) -> Clip:
    """Apply change to clip clip_id's row, check its tracks
    (timeline.track_problems: 422) and store them with their props' defaults
    filled in, then return the clip; 404 if it does not exist, 409 while it
    renders."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        current = row.to_model()
        change(row, current)
        length = clip_length(current, config.settings.render.fps)
        assets = timeline_assets(session, row.tracks)
        problems = track_problems(row.tracks, length, assets, available_fonts())
        if problems:
            raise ApiError(422, "validation_error", "; ".join(problems))
        row.tracks = tidy_props(row.tracks)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()
