"""AI emphasis words and emojis of a clip's captions (SPEC-v2 3.4).

The system prompt is prompts/caption_emphasis.md with the JSON Schema of
WordMarks; the user message lists the caption words of the clip, numbered
(caption_lines.clip_words, with the clip's caption_overrides). The reply's
word numbers become "ai" CaptionMarks at the words' source times. The marks
live in the clip's caption_style.word_marks next to the editor's "user"
marks, which beat them (caption_lines.resolve_marks), so the editor can
change or clear any word the AI marked and a new AI pass keeps those edits.
An invalid reply is sent back with its validation errors, as curate does.
"""

import json
import logging
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from clipforge.llm import LLMClient, reply_json
from clipforge.models import CaptionMark, CaptionStyle, Clip, Transcript, WordMarks
from clipforge.pipeline.caption_lines import CaptionWord, clip_words, to_ms
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, describe_errors, fill
from clipforge.pipeline.step import TRANSCRIPT, load_json

logger = logging.getLogger(__name__)

PROMPT = PROMPTS_DIR / "caption_emphasis.md"


class CaptionEmphasisError(RuntimeError):
    """The LLM sent no valid marks for a clip's words."""


def system_prompt() -> str:
    """Return the system prompt: caption_emphasis.md with WordMarks' JSON
    Schema."""
    schema = json.dumps(WordMarks.model_json_schema(), indent=2)
    return fill(PROMPT, {"schema": schema})


def user_prompt(words: Iterable[CaptionWord], errors: str | None = None) -> str:
    """Return the user message that lists words, one per line as
    "<number>: <text>".

    errors, given when the previous reply was not valid, is added with a
    request to reply again.
    """
    text = "The words of the clip:\n" + "\n".join(
        f"{number}: {word.text}" for number, word in enumerate(words)
    )
    if errors is None:
        return text
    return (
        f"{text}\n\n"
        f"Your previous reply was not valid:\n{errors}\n\n"
        "Reply again with only the JSON object described in the instructions."
    )


def parse_reply(reply: str) -> WordMarks:
    """Return the marks in an LLM reply (unwrapped from a Markdown code
    block); raise ValidationError if it is not valid."""
    return WordMarks.model_validate_json(reply_json(reply))


def ai_marks(
    marks: WordMarks, words: list[CaptionWord], start: float
) -> list[CaptionMark]:
    """Return marks as "ai" CaptionMarks of words, the caption words of a clip
    that starts at start source seconds, in word order.

    A mark of a word that does not exist, or that asks for neither emphasis
    nor an emoji, is left out; two marks of one word are merged.
    """
    first = to_ms(start)
    found: dict[int, CaptionMark] = {}
    for mark in marks.marks:
        if mark.index >= len(words):
            logger.warning("the LLM marked word %d of %d", mark.index, len(words))
            continue
        if not (mark.emphasis or mark.emoji):
            continue
        previous = found.get(mark.index)
        emphasis = mark.emphasis or (previous is not None and previous.emphasis)
        emoji = mark.emoji or (previous.emoji if previous else None)
        found[mark.index] = CaptionMark(
            start=(first + words[mark.index].start) / 1000,
            emphasis=True if emphasis else None,
            emoji=emoji,
            source="ai",
        )
    return [found[index] for index in sorted(found)]


def generate_marks(llm: LLMClient, work: Path, clip: Clip) -> list[CaptionMark]:
    """Ask llm which words of clip, whose transcript is read from work, the
    work directory of its process job, to emphasize and give an emoji.

    An invalid reply is sent back with its errors up to MAX_RETRIES times.
    Returns [] for a clip without words. Raises CaptionEmphasisError if no
    reply was valid, LLMError if the LLM cannot be reached, and StepError if
    the transcript is missing.
    """
    transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    words = clip_words(transcript, clip.start, clip.end, clip.caption_overrides)
    if not words:
        return []
    system, errors = system_prompt(), None
    for attempt in range(1, MAX_RETRIES + 2):
        reply = llm.complete_json(system, user_prompt(words, errors))
        try:
            return ai_marks(parse_reply(reply), words, clip.start)
        except ValidationError as exc:
            errors = describe_errors(exc)
            logger.warning(
                "clip %d: marks reply %d of %d is not valid:\n%s",
                clip.id,
                attempt,
                MAX_RETRIES + 1,
                errors,
            )
    raise CaptionEmphasisError(
        f"the LLM sent no valid marks for clip {clip.id} in {MAX_RETRIES + 1} tries"
    )


def with_ai_marks(style: CaptionStyle, marks: Iterable[CaptionMark]) -> CaptionStyle:
    """Return style with marks as its AI marks: the editor's "user" marks are
    kept, the AI marks that style had before are replaced."""
    kept = [mark for mark in style.word_marks or [] if mark.source == "user"]
    return style.model_copy(update={"word_marks": [*kept, *marks]})
