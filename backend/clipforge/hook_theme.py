"""A viral hook line about a clip's theme from the LLM (POST
/clips/{id}/hook with source "theme", SPEC-v2 3.5), and one line of text
from the LLM for a clip in general (ask_line; the headline's too).

The system prompt is prompts/hook_theme.md (or the caller's) with the JSON
Schema of HookLine; the user message holds the words of the clip as its render shows
them (clip_text.clip_words) and its title. An invalid reply is sent back
with its validation errors, as curate does.
"""

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from clipforge.clip_text import clip_words
from clipforge.llm import LLMClient, reply_json
from clipforge.models import Clip, HookLine
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, describe_errors, fill

logger = logging.getLogger(__name__)

PROMPT = PROMPTS_DIR / "hook_theme.md"


class HookThemeError(RuntimeError):
    """The LLM sent no valid line (a hook line or a headline) for a clip."""


def system_prompt(prompt: Path = PROMPT) -> str:
    """Return the system prompt: prompt (hook_theme.md by default) with
    HookLine's JSON Schema."""
    schema = json.dumps(HookLine.model_json_schema(), indent=2)
    return fill(prompt, {"schema": schema})


def user_prompt(clip: Clip, words: str, errors: str | None = None) -> str:
    """Return the user message for clip, whose render says words; errors,
    given when the previous reply was not valid, asks to reply again."""
    text = f"What is said in the clip:\n{words or '(nothing)'}\n\nTitle: {clip.title}"
    if errors is None:
        return text
    return (
        f"{text}\n\nYour previous reply was not valid:\n{errors}\n\n"
        "Reply again with only the JSON object described in the instructions."
    )


def theme_hook_text(llm: LLMClient, work: Path, clip: Clip) -> str:
    """Ask llm for a hook line about the theme of clip, whose words are
    read from work, the work directory of its process job, and return it
    (whitespace collapsed; errors: see ask_line). Raises StepError if the
    transcript is missing."""
    return ask_line(llm, PROMPT, clip, clip_words(work, clip), "hook line")


def ask_line(llm: LLMClient, prompt: Path, clip: Clip, words: str, what: str) -> str:
    """Ask llm, with the system prompt prompt (system_prompt), for one line
    of text (what it is: "hook line", "headline") for clip, whose render
    says words, and return it with whitespace collapsed and outer quotes
    left off.

    An invalid reply is sent back with its errors up to MAX_RETRIES times.
    Raises HookThemeError if no reply was valid and LLMError if the LLM
    cannot be reached.
    """
    system = system_prompt(prompt)
    errors = None
    for attempt in range(1, MAX_RETRIES + 2):
        reply = llm.complete_json(system, user_prompt(clip, words, errors))
        try:
            line = HookLine.model_validate_json(reply_json(reply))
        except ValidationError as exc:
            errors = describe_errors(exc)
            logger.warning(
                "clip %d: %s reply %d of %d is not valid:\n%s",
                clip.id,
                what,
                attempt,
                MAX_RETRIES + 1,
                errors,
            )
            continue
        text = " ".join(line.text.split()).strip("\"'“”")
        if text:
            return text
        errors = "text: the line is empty"
    raise HookThemeError(
        f"the LLM sent no valid {what} for clip {clip.id} in {MAX_RETRIES + 1} tries"
    )
