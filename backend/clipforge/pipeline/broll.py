"""B-roll spots of a clip (SPEC-v2 3.6): the sentences that the LLM picks
for stock footage, the search words it gives, and the B-roll track items
that show the footage chosen.

A clip's sentences are its rendered words (times in the rendered clip,
after its cuts) split at sentence-ending punctuation, at pauses of
SENTENCE_PAUSE_MS or after SENTENCE_WORDS_MAX words (clip_sentences); the
prompt (prompts/broll.md) numbers them. The LLM picks sentences and
keywords (BrollPick); a reply that is not valid is sent back with its
errors (find_spots). Each pick becomes a spot to review (plan_spots): its
B-roll shows from the sentence's first word for MIN_SPOT_S to MAX_SPOT_S.
The API searches the stock providers with the spot's query and puts the
footage the owner picks on the clip's broll track as a full-screen
cutaway or a picture-in-picture (broll_item; ids ITEM_PREFIX-<n>).

This module does no stock searches or downloads (clipforge.stock, used by
api/broll) so that the pipeline does not depend on the database.
"""

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from clipforge.aspect import aspect_size
from clipforge.llm import LLMClient, reply_json
from clipforge.models import (
    BrollMode,
    BrollPick,
    BrollProps,
    BrollReply,
    BrollSpot,
    Timeline,
    TrackItem,
    TrackItemKind,
)
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, describe_errors, fill

logger = logging.getLogger(__name__)

PROMPT = PROMPTS_DIR / "broll.md"
ITEM_PREFIX = "broll"
# A sentence ends at a word that ends with one of these, at a pause this
# long (ms) before the next word, or after this many words.
SENTENCE_END = re.compile(r"[.!?…]+[\"'”’)\]]*$")
SENTENCE_PAUSE_MS = 800
SENTENCE_WORDS_MAX = 40
# How long a spot's B-roll shows: from its sentence's first word to at
# least MIN_SPOT_S after it (the sentence's end if later), at most
# MAX_SPOT_S; a spot that the clip's end cuts below MIN_SPOT_S is dropped.
MIN_SPOT_S, MAX_SPOT_S = 1.5, 5.0


class BrollError(RuntimeError):
    """The LLM sent no valid B-roll spots for a clip."""


@dataclass(frozen=True)
class Sentence:
    """A sentence of a rendered clip: its text, said from start to end
    seconds of the clip."""

    text: str
    start: float
    end: float


def clip_sentences(words: Sequence[CaptionWord]) -> list[Sentence]:
    """Return the sentences that words (times in milliseconds of the
    rendered clip) say, in order; blank words are skipped."""
    sentences: list[Sentence] = []
    current: list[CaptionWord] = []
    spoken = [word for word in words if word.text.strip()]
    for index, word in enumerate(spoken):
        current.append(word)
        following = spoken[index + 1] if index + 1 < len(spoken) else None
        if (
            following is None
            or SENTENCE_END.search(word.text.strip())
            or following.start - word.end >= SENTENCE_PAUSE_MS
            or len(current) >= SENTENCE_WORDS_MAX
        ):
            text = " ".join(w.text.strip() for w in current)
            sentences.append(Sentence(text, current[0].start / 1000, word.end / 1000))
            current = []
    return sentences


def system_prompt(max_spots: int) -> str:
    """Return the system prompt: broll.md asking for at most max_spots
    spots, with BrollReply's JSON Schema."""
    schema = json.dumps(BrollReply.model_json_schema(), indent=2)
    return fill(PROMPT, {"schema": schema, "max_spots": str(max_spots)})


def user_prompt(sentences: Sequence[Sentence], errors: str | None = None) -> str:
    """Return the user message that lists sentences, one per line as
    "<number>: <start>s-<end>s <text>"; errors, given when the previous
    reply was not valid, asks to reply again."""
    lines = [
        f"{number}: {s.start:.2f}s-{s.end:.2f}s {s.text}"
        for number, s in enumerate(sentences)
    ]
    text = "The sentences of the clip:\n" + "\n".join(lines)
    if errors is None:
        return text
    return (
        f"{text}\n\nYour previous reply was not valid:\n{errors}\n\n"
        "Reply again with only the JSON object described in the instructions."
    )


def pick_problems(
    picks: Sequence[BrollPick], count: int, max_spots: int
) -> list[tuple[int, str]]:
    """Return what is wrong with each of picks for a clip of count
    sentences, as (its index, problem), in order: a sentence the clip does
    not have, the first one (the hook), one picked before or next to an
    earlier usable pick, or a pick past the first max_spots usable ones."""
    problems: list[tuple[int, str]] = []
    usable: list[int] = []
    for index, pick in enumerate(picks):
        number = pick.sentence
        if number >= count:
            problems.append((index, f"sentence {number} does not exist"))
        elif number == 0:
            problems.append((index, "sentence 0 is the hook: show the speaker"))
        elif number in usable:
            problems.append((index, f"sentence {number} is picked twice"))
        elif any(abs(number - other) == 1 for other in usable):
            problems.append((index, f"sentence {number} is next to another spot"))
        elif len(usable) >= max_spots:
            problems.append((index, f"more than {max_spots} spots"))
        else:
            usable.append(number)
    return problems


def find_spots(
    llm: LLMClient, sentences: Sequence[Sentence], max_spots: int, clip_id: int
) -> list[BrollPick]:
    """Ask llm for the B-roll spots of clip clip_id, which says sentences
    (none, and the LLM is not asked, if it says nothing), and return the
    usable picks in time order. A reply that is not valid is sent back with
    its errors up to curate.MAX_RETRIES times; after the last try the
    usable picks of a valid reply are kept. Raises BrollError if no reply
    was valid and LLMError if the LLM cannot be reached."""
    if not sentences:
        return []
    system = system_prompt(max_spots)
    errors, picks = None, None
    for attempt in range(1, MAX_RETRIES + 2):
        reply = llm.complete_json(system, user_prompt(sentences, errors))
        try:
            picks = BrollReply.model_validate_json(reply_json(reply)).spots
        except ValidationError as exc:
            errors = describe_errors(exc)
        else:
            problems = pick_problems(picks, len(sentences), max_spots)
            errors = "\n".join(f"- spots.{i}: {p}" for i, p in problems) or None
            if errors is None:
                break
        logger.warning(
            "clip %d: B-roll reply %d of %d is not valid:\n%s",
            clip_id,
            attempt,
            MAX_RETRIES + 1,
            errors,
        )
    if picks is None:
        raise BrollError(
            f"the LLM sent no valid B-roll spots for clip {clip_id} "
            f"in {MAX_RETRIES + 1} tries"
        )
    wrong = {i for i, _ in pick_problems(picks, len(sentences), max_spots)}
    kept = [pick for index, pick in enumerate(picks) if index not in wrong]
    return sorted(kept, key=lambda pick: pick.sentence)


def spot_window(sentence: Sentence, length: float) -> tuple[float, float] | None:
    """Return when a spot on sentence shows B-roll in a clip whose render
    lasts length seconds (see MIN_SPOT_S, MAX_SPOT_S); None if the clip's
    end leaves it less than MIN_SPOT_S."""
    start = sentence.start
    end = min(max(sentence.end, start + MIN_SPOT_S), start + MAX_SPOT_S, length)
    if end - start < MIN_SPOT_S:
        return None
    return round(start, 3), round(end, 3)


def search_query(keywords: Sequence[str]) -> str:
    """Return the stock search text of keywords: the distinct ones, in
    order, joined by spaces."""
    distinct = dict.fromkeys(word.strip() for word in keywords if word.strip())
    return " ".join(distinct)


def plan_spots(
    picks: Sequence[BrollPick], sentences: Sequence[Sentence], length: float
) -> list[BrollSpot]:
    """Return the spots of picks (usable ones) in a clip whose render lasts
    length seconds, in time order, without search results; a pick whose
    window would overlap an earlier spot's or that the clip's end cuts too
    short is left out (logged)."""
    spots: list[BrollSpot] = []
    for pick in sorted(picks, key=lambda p: sentences[p.sentence].start):
        sentence = sentences[pick.sentence]
        window = spot_window(sentence, length)
        if window is None or (spots and window[0] < spots[-1].end):
            logger.info("B-roll spot on sentence %d left out", pick.sentence)
            continue
        spots.append(
            BrollSpot(
                sentence=pick.sentence,
                text=sentence.text,
                start=window[0],
                end=window[1],
                keywords=list(pick.keywords),
                query=search_query(pick.keywords),
                results=[],
            )
        )
    return spots


def stock_orientation(aspect: str, mode: BrollMode) -> str:
    """Return the shape of stock video that fits B-roll shown in mode in a
    clip of aspect: landscape for picture-in-picture, else the clip's own
    ("portrait", "landscape" or "square")."""
    if mode == "pip":
        return "landscape"
    width, height = aspect_size(aspect)
    if width == height:
        return "square"
    return "landscape" if width > height else "portrait"


def next_item_id(tracks: Timeline) -> str:
    """Return the first ITEM_PREFIX-<n> id (n from 1) that no item of
    tracks has."""
    taken = {
        item.id for name in Timeline.model_fields for item in getattr(tracks, name)
    }
    number = 1
    while f"{ITEM_PREFIX}-{number}" in taken:
        number += 1
    return f"{ITEM_PREFIX}-{number}"


def broll_item(
    item_id: str,
    asset_id: int,
    kind: TrackItemKind,
    start: float,
    end: float,
    props: BrollProps,
    asset_seconds: float | None = None,
) -> TrackItem:
    """Return the broll track item item_id that shows asset asset_id (a
    "video" or "image" item) from start to end seconds with props; a video
    of asset_seconds (from props.offset) ends when the video does, if that
    is sooner."""
    if kind == "video" and asset_seconds is not None:
        playable = asset_seconds - props.offset
        if playable <= 0:
            raise ValueError(f"the video ends before its offset {props.offset:g} s")
        end = min(end, start + playable)
    return TrackItem(
        id=item_id,
        kind=kind,
        asset_id=asset_id,
        start=round(start, 3),
        end=round(end, 3),
        props=props.model_dump(),
    )
