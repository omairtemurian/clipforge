"""The auto headline and motion graphics of a clip from the LLM (SPEC-v2
3.5; POST /clips/{id}/headline and /clips/{id}/motion-graphics), and the
brand template whose style draws them.

The headline is one line (prompts/headline.md, reply HookLine, asked like
a theme hook: hook_theme.ask_line). Motion graphics are picked with
prompts/motion_graphics.md (reply MotionGraphicsReply): a reply that is
not valid, or quotes words the clip does not say, is sent back with its
errors up to MAX_RETRIES times; the picks are then placed on their words
(pipeline/motion_graphics).
"""

import json
import logging
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.brand_style import BrandStyle, brand_style
from clipforge.clip_text import clip_caption_words, clip_words
from clipforge.db import BrandTemplateRow, ProjectRow
from clipforge.fonts import available_fonts
from clipforge.hook_theme import ask_line
from clipforge.llm import LLMClient, reply_json
from clipforge.models import (
    BrandTemplate,
    Clip,
    MotionGraphicPick,
    MotionGraphicsReply,
    TrackItem,
)
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, describe_errors, fill
from clipforge.pipeline.motion_graphics import motion_graphic_items, quote_span
from clipforge.timeline import clip_length

logger = logging.getLogger(__name__)

HEADLINE_PROMPT = PROMPTS_DIR / "headline.md"
MOTION_PROMPT = PROMPTS_DIR / "motion_graphics.md"


class MotionGraphicsError(RuntimeError):
    """The LLM sent no valid motion graphics for a clip."""


def project_brand(session: Session, project_id: int) -> BrandTemplate | None:
    """Return the brand template that project project_id's settings pick;
    None if they pick none, or the project or the template is gone."""
    project = session.get(ProjectRow, project_id)
    if project is None:
        return None
    return settings_brand(session, project.settings.brand_template_id)


def settings_brand(session: Session, template_id: int | None) -> BrandTemplate | None:
    """Return brand template template_id; None for None or a deleted one."""
    if template_id is None:
        return None
    row = session.get(BrandTemplateRow, template_id)
    return row.to_model() if row is not None else None


def brand_style_of(engine: Engine, template_id: int | None) -> BrandStyle | None:
    """Return the style of brand template template_id (brand_style); None
    for None or a deleted template."""
    with Session(engine) as session:
        brand = settings_brand(session, template_id)
    return None if brand is None else brand_style(brand, available_fonts())


def write_headline(llm: LLMClient, work: Path, clip: Clip) -> str:
    """Ask llm for the headline of clip, whose words are read from work,
    the work directory of its process job. Raises HookThemeError if no
    reply was valid, LLMError if the LLM cannot be reached and StepError if
    the transcript is missing."""
    return ask_line(llm, HEADLINE_PROMPT, clip, clip_words(work, clip), "headline")


def motion_system_prompt(max_items: int) -> str:
    """Return the system prompt: motion_graphics.md asking for at most
    max_items graphics, with MotionGraphicsReply's JSON Schema."""
    schema = json.dumps(MotionGraphicsReply.model_json_schema(), indent=2)
    return fill(MOTION_PROMPT, {"schema": schema, "max_items": str(max_items)})


def motion_user_prompt(clip: Clip, words: str, errors: str | None = None) -> str:
    """Return the user message for clip, whose render says words; errors,
    given when the previous reply was not valid, asks to reply again."""
    text = f"What is said in the clip:\n{words or '(nothing)'}\n\nTitle: {clip.title}"
    if errors is None:
        return text
    return (
        f"{text}\n\nYour previous reply was not valid:\n{errors}\n\n"
        "Reply again with only the JSON object described in the instructions."
    )


def pick_motion_graphics(
    llm: LLMClient, clip: Clip, words: Sequence[CaptionWord], max_items: int
) -> list[MotionGraphicPick]:
    """Ask llm for at most max_items motion graphics of clip, whose render
    says words, and return its picks.

    A reply that is not valid, or has a pick whose quote words never say,
    is sent back with its errors up to MAX_RETRIES times; after the last
    try a valid reply is returned as it is (unsaid quotes are left out
    when placed). Raises MotionGraphicsError if no reply was valid and
    LLMError if the LLM cannot be reached.
    """
    system = motion_system_prompt(max_items)
    said = " ".join(word.text for word in words)
    errors, picks = None, None
    for attempt in range(1, MAX_RETRIES + 2):
        reply = llm.complete_json(system, motion_user_prompt(clip, said, errors))
        try:
            picks = MotionGraphicsReply.model_validate_json(reply_json(reply)).items
        except ValidationError as exc:
            errors = describe_errors(exc)
        else:
            errors = _unsaid(picks, words)
            if errors is None:
                return picks
        logger.warning(
            "clip %d: motion graphics reply %d of %d is not valid:\n%s",
            clip.id,
            attempt,
            MAX_RETRIES + 1,
            errors,
        )
    if picks is not None:
        return picks
    raise MotionGraphicsError(
        f"the LLM sent no valid motion graphics for clip {clip.id} "
        f"in {MAX_RETRIES + 1} tries"
    )


def place_motion_graphics(
    llm: LLMClient,
    work: Path,
    clip: Clip,
    style: BrandStyle,
    max_items: int,
    fps: int,
) -> list[TrackItem]:
    """Return the motion graphic items of clip (at most max_items, in
    style) that llm picks from its words, read from work and timed in its
    render at fps. Errors: see pick_motion_graphics; StepError if the
    transcript is missing."""
    words = clip_caption_words(work, clip)
    picks = pick_motion_graphics(llm, clip, words, max_items)
    length = clip_length(clip, fps)
    return motion_graphic_items(picks, words, length, style, max_items)


def _unsaid(
    picks: Sequence[MotionGraphicPick], words: Sequence[CaptionWord]
) -> str | None:
    """Return the errors of picks whose quote words do not say, as
    describe_errors lists them; None if every quote is said."""
    lines = [
        f"- items.{index}.quote: {pick.quote!r} is not said word for word in the clip"
        for index, pick in enumerate(picks)
        if quote_span(words, pick.quote) is None
    ]
    return "\n".join(lines) or None
