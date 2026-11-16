"""Translate a clip's captions into another language with the LLM (SPEC-v2
3.4).

The clip's caption words (caption_lines.clip_words, with its
caption_overrides) go into cues (pipeline/caption_cues); the user message
names the target language and lists the cues, numbered, and the system
prompt is prompts/caption_translate.md with the JSON Schema of
TranslatedCues. Every cue must come back translated once: the translation
keeps each cue's time, so its words show while the cue's words are said.
An invalid reply is sent back with its errors, as curate does.

The result goes into the clip's caption_style.translation, which render,
the SRT export and the editor then show instead of the transcript's words
(polish.rendered_words). Persian, Arabic and Hebrew show right to left in
a bundled font of their script (fonts.covering_font,
caption_effects.encoding).
"""

import json
import logging
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from clipforge.languages import WHISPER_LANGUAGES
from clipforge.llm import LLMClient, reply_json
from clipforge.models import (
    CaptionCue,
    CaptionTranslation,
    Clip,
    Transcript,
    TranslatedCues,
)
from clipforge.pipeline.caption_cues import source_cues
from clipforge.pipeline.caption_lines import clip_words
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, describe_errors, fill
from clipforge.pipeline.step import TRANSCRIPT, load_json

logger = logging.getLogger(__name__)

PROMPT = PROMPTS_DIR / "caption_translate.md"


class CaptionTranslateError(RuntimeError):
    """The LLM sent no valid translation of a clip's captions."""


class CueCountError(ValueError):
    """A reply does not translate every cue exactly once."""


def system_prompt() -> str:
    """Return the system prompt: caption_translate.md with TranslatedCues'
    JSON Schema."""
    schema = json.dumps(TranslatedCues.model_json_schema(), indent=2)
    return fill(PROMPT, {"schema": schema})


def user_prompt(
    cues: Sequence[CaptionCue],
    language: str,
    source_language: str,
    errors: str | None = None,
) -> str:
    """Return the user message: the target language (by name and code), the
    language of the clip and cues, one per line as "<number>: <text>".

    errors, given when the previous reply was not valid, is added with a
    request to reply again.
    """
    target = WHISPER_LANGUAGES.get(language, language)
    source = WHISPER_LANGUAGES.get(source_language, source_language)
    text = (
        f"Translate into: {target} ({language})\n"
        f"The clip is in: {source} ({source_language})\n\n"
        "The caption cues of the clip:\n"
        + "\n".join(f"{number}: {cue.text}" for number, cue in enumerate(cues))
    )
    if errors is None:
        return text
    return (
        f"{text}\n\n"
        f"Your previous reply was not valid:\n{errors}\n\n"
        "Reply again with only the JSON object described in the instructions."
    )


def parse_reply(reply: str, count: int) -> list[str]:
    """Return the translated texts of the count cues in an LLM reply
    (unwrapped from a Markdown code block), in cue order.

    Raises ValidationError if the reply is not valid TranslatedCues, and
    CueCountError unless it translates each of the cues 0..count-1 once.
    """
    cues = TranslatedCues.model_validate_json(reply_json(reply)).cues
    texts: dict[int, str] = {}
    for cue in cues:
        if cue.index >= count:
            raise CueCountError(f"- cues: there is no cue {cue.index}")
        if cue.index in texts:
            raise CueCountError(f"- cues: cue {cue.index} is translated twice")
        texts[cue.index] = cue.text.strip()
    missing = [str(index) for index in range(count) if index not in texts]
    if missing:
        raise CueCountError(f"- cues: no translation of cue {', '.join(missing)}")
    return [texts[index] for index in range(count)]


def translate_captions(
    llm: LLMClient, work: Path, clip: Clip, language: str
) -> CaptionTranslation:
    """Ask llm to translate the captions of clip, whose transcript is read
    from work (the work directory of its process job), into language (a
    Whisper code), and return the translation: each cue with its time.

    An invalid reply is sent back with its errors up to MAX_RETRIES times.
    A clip without words gets a translation without cues. Raises
    CaptionTranslateError if no reply was valid, LLMError if the LLM cannot
    be reached, and StepError if the transcript is missing.
    """
    transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    words = clip_words(transcript, clip.start, clip.end, clip.caption_overrides)
    cues = source_cues(words, clip.start)
    if not cues:
        return CaptionTranslation(language=language, cues=[])
    system, errors = system_prompt(), None
    for attempt in range(1, MAX_RETRIES + 2):
        prompt = user_prompt(cues, language, transcript.language, errors)
        reply = llm.complete_json(system, prompt)
        try:
            texts = parse_reply(reply, len(cues))
        except ValidationError as exc:
            errors = describe_errors(exc)
        except CueCountError as exc:
            errors = str(exc)
        else:
            translated = [
                cue.model_copy(update={"text": text})
                for cue, text in zip(cues, texts, strict=True)
            ]
            return CaptionTranslation(language=language, cues=translated)
        logger.warning(
            "clip %d: translation reply %d of %d is not valid:\n%s",
            clip.id,
            attempt,
            MAX_RETRIES + 1,
            errors,
        )
    raise CaptionTranslateError(
        f"the LLM sent no valid translation of clip {clip.id} "
        f"in {MAX_RETRIES + 1} tries"
    )
