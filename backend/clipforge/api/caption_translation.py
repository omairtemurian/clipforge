"""Caption translation endpoints (SPEC-v2 3.4): the LLM translates a clip's
captions into another language, which render then shows instead of the
transcript's words (pipeline/caption_translate).

    POST   /clips/{id}/caption-translation   CaptionTranslationRequest -> Clip
    DELETE /clips/{id}/caption-translation   -> Clip

The translation is saved in the clip's caption_style.translation; the
editor can also change its cues with PATCH /clips/{id}.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import usage
from clipforge.api.deps import clip_row, get_engine, get_llm, work_dir
from clipforge.api.errors import ApiError
from clipforge.llm import LLMClient
from clipforge.llm_http import LLMError
from clipforge.models import CaptionTranslation, CaptionTranslationRequest, Clip
from clipforge.pipeline.caption_translate import (
    CaptionTranslateError,
    translate_captions,
)
from clipforge.pipeline.step import StepError

logger = logging.getLogger(__name__)

router = APIRouter()


def save_translation(
    engine: Engine, clip_id: int, translation: CaptionTranslation | None
) -> Clip:
    """Set the clip's caption_style.translation (None: the transcript's words
    show again), save it and return the clip."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        row.caption_style = row.caption_style.model_copy(
            update={"translation": translation}
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


@router.post("/clips/{clip_id}/caption-translation")
def translate_clip_captions(
    clip_id: int,
    body: CaptionTranslationRequest,
    engine: Annotated[Engine, Depends(get_engine)],
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> Clip:
    """Translate the clip's captions into body.language from its words
    (caption_translate.translate_captions), save the translation and return
    the clip. Answers 502 if the LLM cannot be reached or sends no valid
    translation, and 409 if the clip's transcript is missing."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        work = work_dir(session, clip.project_id)
    try:
        with usage.recording(engine, clip.project_id):
            translation = translate_captions(llm, work, clip, body.language)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    except (LLMError, CaptionTranslateError) as exc:
        logger.warning("clip %d: no caption translation: %s", clip_id, exc)
        raise ApiError(502, "llm_error", str(exc)) from exc
    return save_translation(engine, clip_id, translation)


@router.delete("/clips/{clip_id}/caption-translation")
def remove_caption_translation(
    clip_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Remove the clip's caption translation, so its captions show the
    transcript's words again, and return the clip."""
    return save_translation(engine, clip_id, None)
