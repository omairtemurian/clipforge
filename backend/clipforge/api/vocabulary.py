"""Brand vocabulary endpoints (SPEC-v2 3.4):

    GET  /vocabulary                          -> Vocabulary
    PUT  /vocabulary                          Vocabulary -> Vocabulary
    POST /projects/{id}/replace-everywhere    ReplaceRequest -> ReplaceResult

The terms are Whisper's hotwords and the corrections are applied to every
transcript (pipeline/transcribe), so they take effect for projects processed
after the change; replace-everywhere changes one project that exists.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import vocabulary
from clipforge.api.deps import get_engine, project_row
from clipforge.api.errors import ApiError
from clipforge.job_rows import process_work_dir
from clipforge.models import ReplaceRequest, ReplaceResult, Vocabulary
from clipforge.pipeline.step import StepError

router = APIRouter()


def _saved() -> Vocabulary:
    """Return the saved vocabulary; 409 if its file is not valid."""
    try:
        return vocabulary.load_vocabulary()
    except vocabulary.VocabularyError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc


@router.get("/vocabulary")
def get_vocabulary() -> Vocabulary:
    """Return the brand vocabulary (empty if none was saved)."""
    return _saved()


@router.put("/vocabulary")
def put_vocabulary(body: Vocabulary) -> Vocabulary:
    """Save body as the brand vocabulary and return it."""
    vocabulary.save_vocabulary(body)
    return body


@router.post("/projects/{project_id}/replace-everywhere")
def replace_everywhere(
    project_id: int,
    body: ReplaceRequest,
    engine: Annotated[Engine, Depends(get_engine)],
) -> ReplaceResult:
    """Change the words body.find into body.replace in the project's
    transcript and all its clips, and return what changed. With
    body.remember the change is also saved as a correction of the
    vocabulary, for later transcripts."""
    with Session(engine) as session:
        project_row(session, project_id)
        try:
            work = process_work_dir(session, project_id)
        except StepError:
            work = None
    remembered = _remembered(body) if body.remember else None
    result = vocabulary.replace_everywhere(
        engine, project_id, work, body.find, body.replace
    )
    if remembered is not None:
        vocabulary.save_vocabulary(remembered)
    return result


def _remembered(body: ReplaceRequest) -> Vocabulary:
    """Return the saved vocabulary with body as a correction; 422 if that
    makes more corrections than a vocabulary holds."""
    saved = _saved()
    corrections = {
        heard: correct
        for heard, correct in saved.corrections.items()
        if heard.casefold() != body.find.casefold()
    }
    corrections[body.find] = body.replace
    try:
        return Vocabulary(terms=saved.terms, corrections=corrections)
    except ValidationError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
