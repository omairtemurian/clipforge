"""New title, description and hashtags of a clip from the LLM
(POST /clips/{id}/regenerate-text).

The system prompt is prompts/clip_text.md with the JSON Schema of ClipText;
the user message holds the words of the clip as its render shows them (its
caption overrides applied, its cut ranges left out) and its current text.
An invalid reply is sent back with its validation errors, as curate does.
"""

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from clipforge import config
from clipforge.llm import LLMClient, reply_json
from clipforge.models import Clip, ClipText, Transcript
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, describe_errors, fill
from clipforge.pipeline.polish import rendered_words
from clipforge.pipeline.step import TRANSCRIPT, load_json

logger = logging.getLogger(__name__)

PROMPT = PROMPTS_DIR / "clip_text.md"


class ClipTextError(RuntimeError):
    """The LLM sent no valid text for a clip."""


def system_prompt() -> str:
    """Return the system prompt: clip_text.md with ClipText's JSON Schema."""
    schema = json.dumps(ClipText.model_json_schema(), indent=2)
    return fill(PROMPT, {"schema": schema})


def user_prompt(clip: Clip, words: str, errors: str | None = None) -> str:
    """Return the user message for clip, whose render says words.

    errors, given when the previous reply was not valid, is added with a
    request to reply again.
    """
    text = (
        f"What is said in the clip:\n{words or '(nothing)'}\n\n"
        f"Current title: {clip.title}\n"
        f"Current hook: {clip.hook_text}\n"
        f"Current description: {clip.description}\n"
        f"Current hashtags: {', '.join(clip.hashtags)}"
    )
    if errors is None:
        return text
    return (
        f"{text}\n\n"
        f"Your previous reply was not valid:\n{errors}\n\n"
        "Reply again with only the JSON object described in the instructions."
    )


def parse_reply(reply: str) -> ClipText:
    """Return the text in an LLM reply (unwrapped from a Markdown code block);
    raise ValidationError if it is not valid."""
    return ClipText.model_validate_json(reply_json(reply))


def clip_words(work: Path, clip: Clip) -> str:
    """Return the words of clip as its render shows them, from work's
    transcript.json; raises StepError if it is missing or not valid."""
    return " ".join(word.text for word in clip_caption_words(work, clip))


def clip_caption_words(work: Path, clip: Clip) -> list[CaptionWord]:
    """Return the words of clip as its render shows them, timed in
    milliseconds of the rendered clip (polish.rendered_words), from work's
    transcript.json; raises StepError if it is missing or not valid."""
    transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    return rendered_words(transcript, clip, config.settings.render.fps)


def regenerate_text(llm: LLMClient, work: Path, clip: Clip) -> ClipText:
    """Ask llm for a new title, description and hashtags of clip, whose
    words are read from work, the work directory of its process job.

    An invalid reply is sent back with its errors up to MAX_RETRIES times.
    Raises ClipTextError if no reply was valid, LLMError if the LLM cannot
    be reached, and StepError if the transcript is missing.
    """
    system, words = system_prompt(), clip_words(work, clip)
    errors = None
    for attempt in range(1, MAX_RETRIES + 2):
        reply = llm.complete_json(system, user_prompt(clip, words, errors))
        try:
            return parse_reply(reply)
        except ValidationError as exc:
            errors = describe_errors(exc)
            logger.warning(
                "clip %d: text reply %d of %d is not valid:\n%s",
                clip.id,
                attempt,
                MAX_RETRIES + 1,
                errors,
            )
    raise ClipTextError(
        f"the LLM sent no valid text for clip {clip.id} in {MAX_RETRIES + 1} tries"
    )
