"""Viral hook endpoints (SPEC-v2 3.5): the hook templates, and a clip's
hook over the first 2-3 s of its render (pipeline/hooks).

GET /hook-templates lists the templates. POST /clips/{id}/hook gives the
clip a hook from a template, its text from the opening words of its
captions, a line the LLM writes about its theme or the text given; PATCH
changes its template, text or seconds; DELETE removes it. Each answers the
clip: 404 if it does not exist, 409 while it renders, 422 for an unknown
template. A change stores a version (undo). The rendered video is not
changed: render the clip again to apply it.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import usage
from clipforge.api.deps import clip_row, get_engine, get_llm, work_dir
from clipforge.api.errors import ApiError
from clipforge.clip_text import clip_words
from clipforge.hook_theme import HookThemeError, theme_hook_text
from clipforge.hooks_templates import HookTemplate, get_template, load_templates
from clipforge.llm import LLMClient
from clipforge.llm_http import LLMError
from clipforge.models import (
    Clip,
    ClipHook,
    HookApply,
    HookEdit,
    HookTemplateInfo,
)
from clipforge.pipeline.hooks import caption_hook_text
from clipforge.pipeline.step import StepError

logger = logging.getLogger(__name__)

router = APIRouter()

HookChange = Callable[[ClipHook | None], ClipHook | None]


@router.get("/hook-templates")
def list_hook_templates() -> list[HookTemplateInfo]:
    """Return the hook templates, in name order."""
    return [template.info(name) for name, template in load_templates().items()]


@router.post("/clips/{clip_id}/hook")
def apply_hook(
    clip_id: int,
    body: HookApply,
    engine: Annotated[Engine, Depends(get_engine)],
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> Clip:
    """Give the clip a hook from body's template (replacing any it has),
    for body.duration seconds (null: the template's), with the text that
    body.source says.

    The captions and theme sources read the clip's words: 409 if its
    transcript is missing; captions with no words to take is 422. theme
    answers 502 if the LLM cannot be reached or sends no valid line.
    """
    template = _template(body.template)
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        work = work_dir(session, clip.project_id) if body.source != "text" else None
    text = body.text or _source_text(engine, llm, clip, work, body.source)
    hook = ClipHook(
        template=body.template,
        text=text,
        duration=template.duration if body.duration is None else body.duration,
    )
    return _save(engine, clip_id, lambda _: hook)


@router.patch("/clips/{clip_id}/hook")
def edit_hook(
    clip_id: int, body: HookEdit, engine: Annotated[Engine, Depends(get_engine)]
) -> Clip:
    """Change the fields of the clip's hook that body sets; 404 if the clip
    has no hook."""
    if body.template is not None:
        _template(body.template)
    changes = body.model_dump(exclude_none=True)

    def edit(hook: ClipHook | None) -> ClipHook:
        """Return hook with body's changes."""
        if hook is None:
            raise ApiError(404, "not_found", f"clip {clip_id} has no hook")
        return ClipHook.model_validate(hook.model_dump() | changes)

    return _save(engine, clip_id, edit)


@router.delete("/clips/{clip_id}/hook")
def remove_hook(clip_id: int, engine: Annotated[Engine, Depends(get_engine)]) -> Clip:
    """Remove the clip's hook (a clip without one is answered as it is)."""
    return _save(engine, clip_id, lambda _: None)


def _template(name: str) -> HookTemplate:
    """Return the hook template called name; 422 if there is none."""
    try:
        return get_template(name)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc


def _source_text(
    engine: Engine, llm: LLMClient, clip: Clip, work: Path | None, source: str
) -> str:
    """Return the hook text of clip from source ("captions" or "theme"),
    reading its words from work (errors: see apply_hook)."""
    assert work is not None
    try:
        if source == "captions":
            text = caption_hook_text(clip_words(work, clip).split())
            if not text:
                raise ApiError(
                    422, "validation_error", f"clip {clip.id} has no words for a hook"
                )
            return text
        with usage.recording(engine, clip.project_id):
            return theme_hook_text(llm, work, clip)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    except (LLMError, HookThemeError) as exc:
        logger.warning("clip %d: no hook line: %s", clip.id, exc)
        raise ApiError(502, "llm_error", str(exc)) from exc


def _save(engine: Engine, clip_id: int, change: HookChange) -> Clip:
    """Store change(the clip's hook) as clip clip_id's hook and return the
    clip; 404 if it does not exist, 409 while it renders."""
    with Session(engine) as session:
        row = clip_row(session, clip_id)
        if row.status == "rendering":
            raise ApiError(409, "conflict", f"clip {clip_id} is rendering; try later")
        hook = change(row.hook)
        if hook != row.hook:
            row.hook = hook
            session.add(row)
            session.commit()
            session.refresh(row)
        return row.to_model()
