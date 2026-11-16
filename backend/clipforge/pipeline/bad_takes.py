"""Bad takes of a clip (SPEC-v2 3.5 speech cleanup): sentences the speaker
repeats or abandons, which the LLM finds.

The system prompt is prompts/bad_takes.md with BadTakesReply's JSON Schema;
the user message lists the clip's words, numbered, with a "---" line
between sections (take_words: the caption words of its sections in play
order, with its caption_overrides, leaving out the words its cuts remove).

A take the LLM picks (BadTakePick: its first and last word's number)
becomes a "bad_take" suggestion from the start of its first word to the
start of the word after it in its section, so the gap after the take goes
too and the next word follows the gap before it; at a section's end, to
its last word's end. A reply that is not valid, or whose takes name words
the clip does not have, run across sections, overlap or leave no word, is
sent back with its errors up to curate.MAX_RETRIES times; after the last
try the usable takes of a valid reply are kept.
"""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from clipforge.llm import LLMClient, reply_json
from clipforge.models import (
    BadTakePick,
    BadTakesReply,
    CleanupSuggestion,
    Clip,
    Transcript,
)
from clipforge.pipeline.caption_lines import clip_words, to_ms
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, describe_errors, fill

logger = logging.getLogger(__name__)

PROMPT = PROMPTS_DIR / "bad_takes.md"
SECTION_BREAK = "---"


class BadTakesError(RuntimeError):
    """The LLM sent no valid bad takes for a clip."""


@dataclass(frozen=True)
class TakeWord:
    """A spoken word of a clip: its text, its start and end in milliseconds
    of the source, and the number of its section in play order."""

    text: str
    start: int
    end: int
    section: int


def take_words(transcript: Transcript, clip: Clip) -> list[TakeWord]:
    """Return the words of clip as it plays them: the caption words of each
    of its sections in play order (caption_lines.clip_words with its
    caption_overrides), without those that start inside a cut range."""
    cuts = [(to_ms(start), to_ms(end)) for start, end in clip.cut_ranges]
    words: list[TakeWord] = []
    for section, (start, end) in enumerate(clip.segments):
        offset = to_ms(start)
        for word in clip_words(transcript, start, end, clip.caption_overrides):
            begin = offset + word.start
            if not any(cut_start <= begin < cut_end for cut_start, cut_end in cuts):
                words.append(
                    TakeWord(word.text.strip(), begin, offset + word.end, section)
                )
    return words


def system_prompt() -> str:
    """Return the system prompt: bad_takes.md with BadTakesReply's JSON
    Schema."""
    schema = json.dumps(BadTakesReply.model_json_schema(), indent=2)
    return fill(PROMPT, {"schema": schema})


def user_prompt(words: Sequence[TakeWord], errors: str | None = None) -> str:
    """Return the user message that lists words, one per line as
    "<number>: <text>", with SECTION_BREAK between sections; errors, given
    when the previous reply was not valid, asks to reply again."""
    lines: list[str] = []
    for number, word in enumerate(words):
        if number and word.section != words[number - 1].section:
            lines.append(SECTION_BREAK)
        lines.append(f"{number}: {word.text}")
    text = "The words of the clip:\n" + "\n".join(lines)
    if errors is None:
        return text
    return (
        f"{text}\n\nYour previous reply was not valid:\n{errors}\n\n"
        "Reply again with only the JSON object described in the instructions."
    )


def take_problems(
    takes: Sequence[BadTakePick], words: Sequence[TakeWord]
) -> list[tuple[int, str]]:
    """Return what is wrong with each of takes, as (its index, problem), in
    order: a take whose words the clip does not have (first after last, a
    number past its words), that runs across sections or overlaps an
    earlier usable take; or, if the usable ones would leave no word, each
    of them."""
    problems: list[tuple[int, str]] = []
    usable: list[tuple[int, BadTakePick]] = []
    for index, take in enumerate(takes):
        if take.first > take.last or take.last >= len(words):
            problems.append((index, f"words {take.first}-{take.last} do not exist"))
        elif words[take.first].section != words[take.last].section:
            problems.append((index, "runs across a section break (---)"))
        elif any(take.first <= o.last and o.first <= take.last for _, o in usable):
            problems.append((index, "overlaps another take"))
        else:
            usable.append((index, take))
    taken = sum(take.last - take.first + 1 for _, take in usable)
    if usable and taken == len(words):
        problems += [
            (index, "the takes leave no word of the clip") for index, _ in usable
        ]
    return sorted(problems)


def usable_takes(
    takes: Sequence[BadTakePick], words: Sequence[TakeWord]
) -> list[BadTakePick]:
    """Return the takes that take_problems finds nothing wrong with."""
    wrong = {index for index, _ in take_problems(takes, words)}
    return [take for index, take in enumerate(takes) if index not in wrong]


def take_suggestion(take: BadTakePick, words: Sequence[TakeWord]) -> CleanupSuggestion:
    """Return the cut of take (module docstring), a usable take of words."""
    first, last = words[take.first], words[take.last]
    after = take.last + 1
    if after < len(words) and words[after].section == last.section:
        end = words[after].start
    else:
        end = last.end
    text = " ".join(word.text for word in words[take.first : after])
    return CleanupSuggestion(
        start=first.start / 1000, end=end / 1000, kind="bad_take", text=text
    )


def find_bad_takes(
    llm: LLMClient, words: Sequence[TakeWord], clip_id: int
) -> list[CleanupSuggestion]:
    """Ask llm for the bad takes of clip clip_id, which says words, and
    return their cuts in order (none without words, and the LLM is not
    asked). Raises BadTakesError if no reply was valid and LLMError if the
    LLM cannot be reached."""
    if not words:
        return []
    system = system_prompt()
    errors, takes = None, None
    for attempt in range(1, MAX_RETRIES + 2):
        reply = llm.complete_json(system, user_prompt(words, errors))
        try:
            takes = BadTakesReply.model_validate_json(reply_json(reply)).takes
        except ValidationError as exc:
            errors = describe_errors(exc)
        else:
            problems = take_problems(takes, words)
            errors = "\n".join(f"- takes.{i}: {p}" for i, p in problems) or None
            if errors is None:
                break
        logger.warning(
            "clip %d: bad takes reply %d of %d is not valid:\n%s",
            clip_id,
            attempt,
            MAX_RETRIES + 1,
            errors,
        )
    if takes is None:
        raise BadTakesError(
            f"the LLM sent no valid bad takes for clip {clip_id} "
            f"in {MAX_RETRIES + 1} tries"
        )
    picked = sorted(usable_takes(takes, words), key=lambda take: take.first)
    return [take_suggestion(take, words) for take in picked]
