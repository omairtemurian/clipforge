"""Correcting words of a transcript (SPEC-v2 3.4 brand vocabulary).

A correction {heard: correct} replaces the whole words "heard" (any case,
punctuation around them aside) by "correct": "open ai," becomes "OpenAI,".
It works on the pieces of a segment's text between whitespace
(enrich.piece_words), like captions do, so a word Whisper split in two
("Kuber" "netes") is one piece. A corrected piece becomes one word per word
of the replacement, over the time of the words it replaces; the segment's
text is rebuilt from its pieces, so words and text still spell each other.
Words that no correction touches are the same objects as before.
"""

import re
from collections.abc import Mapping

from clipforge.models import Segment, Transcript, Word
from clipforge.pipeline.caption_lines import word_key
from clipforge.pipeline.enrich import piece_words

DECIMALS = 3
# The punctuation at the start and the end of a piece of text.
LEAD = re.compile(r"^\W*")
TRAIL = re.compile(r"\W*$")

# The keys of the words of a phrase, in order.
Phrase = tuple[str, ...]


def phrase_key(text: str) -> Phrase:
    """Return the keys (caption_lines.word_key) of the words of text."""
    return tuple(word_key(piece) for piece in text.split())


def compile_corrections(corrections: Mapping[str, str]) -> dict[Phrase, str]:
    """Return the corrections by the key of the words they match; a
    correction whose words have no letters or digits is left out."""
    compiled: dict[Phrase, str] = {}
    for heard, correct in corrections.items():
        key = phrase_key(heard)
        if key and all(key):
            compiled[key] = correct.strip()
    return compiled


def correct_transcript(
    transcript: Transcript, corrections: Mapping[str, str]
) -> tuple[Transcript, int]:
    """Return transcript with corrections applied (see the module docstring)
    and how many times a correction changed a piece or phrase of it.

    Each correction matches inside one segment; at a place where several
    match, the one with most words wins."""
    compiled = compile_corrections(corrections)
    if not compiled:
        return transcript, 0
    longest = max(len(key) for key in compiled)
    segments: list[Segment] = []
    total = 0
    for segment in transcript.segments:
        fixed, count = _correct_segment(segment, compiled, longest)
        segments.append(fixed)
        total += count
    if total == 0:
        return transcript, 0
    return transcript.model_copy(update={"segments": segments}), total


def _correct_segment(
    segment: Segment, corrections: dict[Phrase, str], longest: int
) -> tuple[Segment, int]:
    """Return segment with corrections applied and the number of changes."""
    groups = piece_words(segment)
    if groups is None:
        groups = [[word] for word in segment.words if word.text.strip()]
    texts = ["".join(word.text.strip() for word in group) for group in groups]
    keys = [word_key(text) for text in texts]
    words: list[Word] = []
    pieces: list[str] = []
    count = 0
    index = 0
    while index < len(groups):
        size = next(
            (
                n
                for n in range(min(longest, len(groups) - index), 0, -1)
                if tuple(keys[index : index + n]) in corrections
            ),
            0,
        )
        if size:
            span = groups[index : index + size]
            lead = LEAD.search(texts[index])
            trail = TRAIL.search(texts[index + size - 1])
            new = (
                (lead.group() if lead else "")
                + corrections[tuple(keys[index : index + size])]
                + (trail.group() if trail else "")
            )
            if new.split() != texts[index : index + size]:
                count += 1
                words += _spread(span, new.split())
                pieces += new.split()
                index += size
                continue
        words += groups[index]
        pieces.append(texts[index])
        index += 1
    if count == 0:
        return segment, 0
    return segment.model_copy(update={"words": words, "text": " ".join(pieces)}), count


def _spread(span: list[list[Word]], texts: list[str]) -> list[Word]:
    """Return one word per text over the time of the words in span: its
    first word's start to its last word's end, split evenly. They take the
    speaker of the first word, the lowest probability, and are approximate if
    any of the words was."""
    flat = [word for group in span for word in group]
    start, end = flat[0].start, flat[-1].end
    step = (end - start) / len(texts)
    return [
        Word(
            text=text,
            start=round(start + step * n, DECIMALS),
            end=round(end if n == len(texts) - 1 else start + step * (n + 1), DECIMALS),
            speaker=flat[0].speaker,
            prob=min(word.prob for word in flat),
            approximate=any(word.approximate for word in flat),
        )
        for n, text in enumerate(texts)
    ]


def replace_text(text: str, heard: str, correct: str) -> tuple[str, int]:
    """Return text with the whole words heard (any case) replaced by correct,
    and how many were replaced. For titles, descriptions and the like."""
    pieces = [re.escape(piece) for piece in heard.split()]
    pattern = re.compile(r"(?<!\w)" + r"\s+".join(pieces) + r"(?!\w)", re.IGNORECASE)
    return pattern.subn(lambda _: correct, text)


def correct_word(text: str, heard: str, correct: str) -> str | None:
    """Return the word text with correct in place of its letters if they
    spell the one word heard (any case, punctuation around it kept), else
    None."""
    if phrase_key(text) != phrase_key(heard) or len(heard.split()) != 1:
        return None
    lead, trail = LEAD.search(text), TRAIL.search(text)
    new = (lead.group() if lead else "") + correct + (trail.group() if trail else "")
    return None if new == text else new
