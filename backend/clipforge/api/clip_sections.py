"""Section op endpoints of a clip (SPEC-v2 3.5): trim or extend a section,
add a part of the source as a section, split one at a time of the source,
delete one, and play the sections in another order.

A clip's sections are its segments, in play order; times are seconds of
the source. Each op answers the edited clip (clip_edit.apply_sections:
the video track, cut ranges and scenes follow the sections), 404 if the
clip or the section does not exist, 409 while the clip renders and 422 if
the op would leave the clip invalid. Every op stores a version (undo). The
rendered video is not changed: render the clip again to apply it.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import clip_edit
from clipforge.api.deps import clip_row, get_engine, project_row
from clipforge.api.errors import ApiError
from clipforge.clip_edit import ClipEditError, SectionNotFound
from clipforge.models import (
    Clip,
    SectionAdd,
    SectionOrder,
    SectionSpan,
    SectionSplit,
    SourceSpan,
)

router = APIRouter()

SectionOp = Callable[[list[SourceSpan], float], list[SourceSpan]]


@router.put("/clips/{clip_id}/sections/{index}")
def trim_section(
    clip_id: int,
    index: int,
    body: SectionSpan,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Clip:
    """Trim or extend section index to body's start..end, clamped to the
    source and to the sections next to it in the source."""
    return _edit(
        engine,
        clip_id,
        lambda spans, duration: clip_edit.trim_section(
            spans, index, body.start, body.end, duration
        ),
    )


@router.post("/clips/{clip_id}/sections")
def add_section(
    clip_id: int, body: SectionAdd, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Add body's start..end of the source (clamped to it) as a section that
    plays at body.index (null: last); 422 if it overlaps a section."""
    return _edit(
        engine,
        clip_id,
        lambda spans, duration: clip_edit.add_section(
            spans, body.start, body.end, duration, body.index
        ),
    )


@router.post("/clips/{clip_id}/sections/split")
def split_section(
    clip_id: int, body: SectionSplit, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Split the section that plays body.at seconds of the source into two
    there; 422 if no section plays that time (inside it)."""
    return _edit(
        engine, clip_id, lambda spans, _: clip_edit.split_section(spans, body.at)
    )


@router.post("/clips/{clip_id}/sections/reorder")
def reorder_sections(
    clip_id: int, body: SectionOrder, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Play the sections in body.order, their current indices each once."""
    return _edit(
        engine,
        clip_id,
        lambda spans, _: clip_edit.reorder_sections(spans, body.order),
    )


@router.delete("/clips/{clip_id}/sections/{index}")
def delete_section(
    clip_id: int, index: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Delete section index; 422 for the clip's only section."""
    return _edit(
        engine, clip_id, lambda spans, _: clip_edit.delete_section(spans, index)
    )


def _edit(engine: Engine, clip_id: int, op: SectionOp) -> Clip:
    """Apply op, given the clip's sections and its source's duration, and
    store the sections it returns (clip_edit.apply_sections); return the
    clip. 404 if the clip or a section op's section does not exist, 409
    while the clip renders, 422 if the result is not valid."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        duration = project_row(session, row.project_id).duration
        try:
            segments = op(list(row.to_model().segments), duration)
            clip_edit.apply_sections(session, row, segments, duration)
        except SectionNotFound as exc:
            raise ApiError(404, "not_found", str(exc)) from exc
        except ClipEditError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc
        return row.to_model()
