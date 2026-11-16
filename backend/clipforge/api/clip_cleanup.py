"""Speech cleanup and enhancement of a clip (SPEC-v2 3.5; pipeline/cleanup,
pipeline/enhance).

GET /filler-languages lists the languages that have a filler list.
POST /clips/{id}/cleanup/preview lists what cleanup would remove from the
saved clip, for review, without changing it: filler words of the chosen
language, pauses longer than the threshold and, if asked, bad takes that
the LLM finds. POST /clips/{id}/cleanup/apply cuts the preview's items
that the user left checked and saves the clip (a version: undo takes it
back). PUT /clips/{id}/enhance sets how strongly the render cleans the
clip's speech (0: off; with DeepFilterNet if it is installed, else with
ffmpeg's filters), a version too. The rendered video is not changed in
either case: render the clip again.

Errors: 404 if the clip does not exist; 409 if the project's transcript or
signals are missing, or (apply) while the clip renders; 422 for a body that
is not valid or cuts that leave nothing of the clip; 502 if the LLM cannot
be reached or sends no valid bad takes.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import usage
from clipforge.api.deps import clip_row, get_engine, get_llm, project_row, work_dir
from clipforge.api.errors import ApiError
from clipforge.clip_edit import ClipEditError, apply_patch
from clipforge.fillers import filler_languages
from clipforge.llm import LLMClient
from clipforge.llm_http import LLMError
from clipforge.models import (
    CleanupApply,
    CleanupOptions,
    CleanupPreview,
    Clip,
    ClipPatch,
    SpeechEnhance,
)
from clipforge.pipeline.bad_takes import BadTakesError, find_bad_takes, take_words
from clipforge.pipeline.cleanup import cleanup_cuts, cleanup_preview
from clipforge.pipeline.polish import load_polish_inputs
from clipforge.pipeline.step import StepError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/filler-languages")
def list_filler_languages() -> list[str]:
    """Return the codes of the languages that have a filler list, sorted
    (any other language uses the English one)."""
    return filler_languages()


@router.post("/clips/{clip_id}/cleanup/preview")
def preview_cleanup(
    clip_id: int,
    body: CleanupOptions,
    engine: Annotated[Engine, Depends(get_engine)],
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> CleanupPreview:
    """Return what speech cleanup with body's options would remove from the
    saved clip (pipeline/cleanup.cleanup_preview); the clip is unchanged."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        work = work_dir(session, clip.project_id)
    try:
        transcript, events = load_polish_inputs(work)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    bad_takes = []
    if body.bad_takes:
        words = take_words(transcript, clip)
        try:
            with usage.recording(engine, clip.project_id):
                bad_takes = find_bad_takes(llm, words, clip.id)
        except (LLMError, BadTakesError) as exc:
            logger.warning("clip %d: no bad takes from the LLM: %s", clip.id, exc)
            raise ApiError(502, "llm_error", str(exc)) from exc
    return cleanup_preview(transcript, events, clip, body, bad_takes)


@router.post("/clips/{clip_id}/cleanup/apply")
def apply_cleanup(
    clip_id: int,
    body: CleanupApply,
    engine: Annotated[Engine, Depends(get_engine)],
) -> Clip:
    """Cut body's items, except the unchecked ones, from the clip
    (pipeline/cleanup.cleanup_cuts) and return the saved clip."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        cuts = cleanup_cuts(row.to_model(), body.items, body.unchecked)
        duration = project_row(session, row.project_id).duration
        try:
            apply_patch(session, row, ClipPatch(cut_ranges=cuts), duration)
        except ClipEditError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc
        return row.to_model()


@router.put("/clips/{clip_id}/enhance")
def set_enhancement(
    clip_id: int, body: SpeechEnhance, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Set the clip's speech enhancement to body.strength and return the
    clip; 404 if it does not exist, 409 while it renders."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        if row.enhance != body.strength:
            row.enhance = body.strength
            session.add(row)
            session.commit()
            session.refresh(row)
        return row.to_model()
