"""The cut endpoints of the editor (SPEC 7): the speech cleanup that polish
suggests for a clip, the silences that auto cut takes out of it (TASK-27)
and the punch-ins of auto zoom (TASK-23). None changes the clip; the editor
saves what it keeps with PATCH."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.api.deps import clip_row, get_engine, project_row, work_dir
from clipforge.api.errors import ApiError
from clipforge.models import (
    CleanupSuggestion,
    CutRange,
    SignalEvent,
    Transcript,
    ZoomKeyframe,
)
from clipforge.pipeline import polish
from clipforge.pipeline.auto_cut import auto_cuts
from clipforge.pipeline.auto_zoom import auto_zoom_keyframes
from clipforge.pipeline.step import StepError

router = APIRouter()

SpanStart = Annotated[float | None, Query(ge=0)]
SpanEnd = Annotated[float | None, Query(gt=0)]


def span_inputs(
    engine: Engine, clip_id: int, start: float | None, end: float | None
) -> tuple[Transcript, list[SignalEvent], float, float, float]:
    """Return the transcript and signal events of the clip's project, the
    span from start to end (default the saved clip's) and the project's
    auto cut min pause. Raises ApiError 404 if the clip does not exist, 422
    unless start < end within the video, 409 if the transcript or signals
    are missing."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        project = project_row(session, clip.project_id)
        duration, settings = project.duration, project.settings
        work = work_dir(session, clip.project_id)
    span_start = clip.start if start is None else start
    span_end = clip.end if end is None else end
    if not span_start < span_end <= max(duration, clip.end):
        raise ApiError(
            422, "validation_error", "start must be before end within the video"
        )
    try:
        transcript, events = polish.load_polish_inputs(work)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    return transcript, events, span_start, span_end, settings.auto_cut_min_pause_s


@router.get("/clips/{clip_id}/cleanup-suggestions")
def get_cleanup_suggestions(
    clip_id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    start: SpanStart = None,
    end: SpanEnd = None,
) -> list[CleanupSuggestion]:
    """Return the filler and pause cuts that polish suggests for the clip
    (polish.cleanup_suggestions), in order, without changing the clip.

    start and end (seconds of the source, default the saved clip's) let the
    editor ask for its unsaved span. 422 unless start < end within the
    video; 409 if the project's transcript or signals are missing.
    """
    transcript, events, span_start, span_end, _ = span_inputs(
        engine, clip_id, start, end
    )
    return polish.cleanup_suggestions(transcript, events, span_start, span_end)


@router.get("/clips/{clip_id}/auto-cuts")
def get_auto_cuts(
    clip_id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    start: SpanStart = None,
    end: SpanEnd = None,
) -> list[CutRange]:
    """Return the cut ranges that auto cut takes out of the clip: its
    silences longer than the project's auto_cut_min_pause_s
    (auto_cut.auto_cuts), in order, without changing the clip.

    start, end and the errors are as for cleanup-suggestions.
    """
    transcript, events, span_start, span_end, pause = span_inputs(
        engine, clip_id, start, end
    )
    return auto_cuts(transcript, events, span_start, span_end, pause)


@router.get("/clips/{clip_id}/auto-zooms")
def get_auto_zooms(
    clip_id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    start: SpanStart = None,
    end: SpanEnd = None,
) -> list[ZoomKeyframe]:
    """Return the zoom keyframes of the punch-ins that auto zoom gives the
    clip, at its emphasis words, its new sentences after the pauses that
    auto cut takes out and its laughs and energy peaks
    (auto_zoom.auto_zoom_keyframes), in order, without changing the clip.

    start, end and the errors are as for cleanup-suggestions.
    """
    transcript, events, span_start, span_end, pause = span_inputs(
        engine, clip_id, start, end
    )
    with Session(engine) as session:
        words = clip_row(session, clip_id).emphasis_words
    return auto_zoom_keyframes(transcript, events, words, span_start, span_end, pause)
