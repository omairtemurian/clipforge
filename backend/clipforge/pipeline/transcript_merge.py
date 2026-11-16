"""Turning Whisper's output for overlapping audio chunks into one Transcript.

The transcribe step (SPEC 6.2) cuts the audio into chunks that overlap and
transcribes each one on its own. This module holds the pure parts of that:
planning the chunks, moving chunk times to source times, splicing consecutive
chunks so that every word of an overlap appears once, and grouping the words
into sentence segments (the form of backend/tests/fixtures/transcript.json).
"""

import difflib
import itertools
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from clipforge.models import Segment, Transcript, Word

# Without diarization every word has the same speaker (SPEC 2).
SPEAKER = "S0"
# Two chunks heard the same word of their overlap if the texts match (case
# and punctuation aside) and the starts are at most this many seconds apart.
SAME_WORD_S = 1.0
# A word ending in one of these, maybe followed by closing quotes or
# brackets, ends a sentence.
SENTENCE_END = re.compile(r"[.!?…。！？]['\"’”)\]]*$")
# Abbreviations whose period does not end a sentence.
ABBREVIATIONS = frozenset(
    {"mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "vs.", "e.g.", "i.e."}
)
# Unpunctuated speech is cut at the end of a Whisper segment once the
# segment so far lasts this many seconds.
MAX_SENTENCE_S = 20.0
# Times and probabilities are rounded to milliseconds / 3 decimals.
DECIMALS = 3


@dataclass(frozen=True, slots=True)
class Chunk:
    """A piece of the audio to transcribe, from start to end source seconds."""

    start: float
    end: float


@dataclass(frozen=True, slots=True)
class TimedWord:
    """A word as Whisper reports it.

    text keeps Whisper's spacing (a leading space in most languages) and
    attached punctuation. start and end are seconds: relative to the chunk as
    Whisper gives them, in source time after merge_chunks. prob is Whisper's
    probability of the word; segment_end marks the last word of a Whisper
    segment; approximate is True for a time spread over a subtitle cue.
    """

    text: str
    start: float
    end: float
    prob: float
    segment_end: bool = False
    approximate: bool = False


def plan_chunks(start: float, end: float, length: float, overlap: float) -> list[Chunk]:
    """Cover [start, end] with chunks of length seconds that overlap.

    Each chunk starts overlap seconds before the previous one ends; the last
    one ends at end and may be shorter. Raises ValueError if end is not after
    start, or overlap is not in [0, length).
    """
    if end <= start:
        raise ValueError(f"nothing to transcribe from {start:g}s to {end:g}s")
    if not 0 <= overlap < length:
        raise ValueError(
            f"chunk overlap ({overlap:g}s) must be >= 0 and shorter than "
            f"the chunk ({length:g}s)"
        )
    chunks: list[Chunk] = []
    chunk_start = start
    while True:
        chunk_end = min(chunk_start + length, end)
        chunks.append(Chunk(chunk_start, chunk_end))
        if chunk_end >= end:
            return chunks
        chunk_start = chunk_end - overlap


def to_source_time(chunk: Chunk, words: Iterable[TimedWord]) -> list[TimedWord]:
    """Return words with their chunk-relative times moved to source time.

    Times are clamped to the chunk: Whisper can place the end of the last
    word after the end of the audio it was given.
    """

    def shift(seconds: float) -> float:
        return min(max(chunk.start + seconds, chunk.start), chunk.end)

    return [replace(w, start=shift(w.start), end=shift(w.end)) for w in words]


def merge_chunks(
    chunks: Sequence[tuple[Chunk, Sequence[TimedWord]]],
) -> list[TimedWord]:
    """Return the words of consecutive, overlapping chunks in source time.

    Each item is a chunk and the words Whisper heard in it (chunk-relative
    times). Every word of an overlap is kept from one chunk only: the chunks
    are spliced at a word both heard, near the middle of the overlap, where
    neither is cut off at its edge (see _splice). In the result, every word
    starts at or after the start of the one before it, and ends at or before
    the start of the one after it.
    """
    merged: list[TimedWord] = []
    previous: Chunk | None = None
    for chunk, words in chunks:
        current = to_source_time(chunk, words)
        if previous is None:
            merged = current
        else:
            merged = _splice(merged, current, chunk.start, previous.end)
        previous = chunk
    return _ordered(merged)


def build_transcript(
    words: Sequence[TimedWord], *, language: str, duration: float
) -> Transcript:
    """Group words (in source time, in order) into a Transcript of sentences.

    A segment ends after a word that ends a sentence (".", "?", "!" or "…",
    maybe before closing quotes; not abbreviations such as "Mr."), or at the
    end of a Whisper segment once it lasts MAX_SENTENCE_S. Word texts are
    stripped; a segment's text is its words as Whisper spaced them. Every
    word and segment gets speaker S0; ids count from 0.
    """
    segments: list[Segment] = []
    pending: list[TimedWord] = []
    for word in words:
        if not word.text.strip():
            continue
        pending.append(word)
        too_long = word.end - pending[0].start >= MAX_SENTENCE_S
        if _ends_sentence(word.text) or (word.segment_end and too_long):
            segments.append(_segment(len(segments), pending))
            pending = []
    if pending:
        segments.append(_segment(len(segments), pending))
    return Transcript(language=language, duration=duration, segments=segments)


def _splice(
    before: list[TimedWord],
    after: list[TimedWord],
    overlap_start: float,
    overlap_end: float,
) -> list[TimedWord]:
    """Join the words of two chunks that overlap from overlap_start to overlap_end.

    If only one chunk heard words in the overlap, they are all kept.
    Otherwise the texts of the two chunks' overlap words are aligned; of the
    aligned pairs that start at most SAME_WORD_S apart, the one closest to
    the middle of the overlap is the splice point: the earlier chunk's words
    before it, then the later chunk's words from it on. Without such a pair,
    each chunk keeps the words whose midpoint is on its side of the middle.
    """
    middle = (overlap_start + overlap_end) / 2
    first = next((i for i, w in enumerate(before) if w.end > overlap_start), None)
    stop = next((j for j, w in enumerate(after) if w.start >= overlap_end), None)
    first = len(before) if first is None else first
    stop = len(after) if stop is None else stop
    if first == len(before) or stop == 0:
        return before + after
    pair = _closest_pair(before[first:], after[:stop], middle)
    if pair is not None:
        i, j = pair
        return before[: first + i] + after[j:]
    kept = [w for w in before if (w.start + w.end) / 2 < middle]
    return kept + [w for w in after if (w.start + w.end) / 2 >= middle]


def _closest_pair(
    earlier: Sequence[TimedWord], later: Sequence[TimedWord], middle: float
) -> tuple[int, int] | None:
    """Return the indexes of the same word in both lists closest to middle.

    The lists are aligned like a diff of their texts, so a repeated word
    ("no, no, no") pairs with its own occurrence; pairs whose starts differ
    by more than SAME_WORD_S, or that have no letters or digits, are not the
    same word. Returns None if no pair is left.
    """
    keys_a, keys_b = [_key(w) for w in earlier], [_key(w) for w in later]
    matcher = difflib.SequenceMatcher(None, keys_a, keys_b, autojunk=False)
    best: tuple[int, int] | None = None
    best_distance = math.inf
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            i, j = block.a + k, block.b + k
            a, b = earlier[i], later[j]
            if not keys_a[i] or abs(a.start - b.start) > SAME_WORD_S:
                continue
            distance = abs((a.start + b.start) / 2 - middle)
            if distance < best_distance:
                best, best_distance = (i, j), distance
    return best


def _key(word: TimedWord) -> str:
    """Return the text of word for matching: lowercase letters and digits."""
    return re.sub(r"\W+", "", word.text.casefold())


def _ordered(words: Sequence[TimedWord]) -> list[TimedWord]:
    """Return words whose times never go back or overlap.

    A start before the previous word's start moves up to it; an end after
    the next word's start moves back to it (and never before the start).
    """
    if not words:
        return []
    starts = list(itertools.accumulate((w.start for w in words), max))
    ends = [*starts[1:], math.inf]
    return [
        replace(w, start=start, end=min(max(w.end, start), next_start))
        for w, start, next_start in zip(words, starts, ends, strict=True)
    ]


def _ends_sentence(text: str) -> bool:
    """True if a word with this text ends a sentence."""
    stripped = text.strip()
    if stripped.casefold() in ABBREVIATIONS:
        return False
    return SENTENCE_END.search(stripped) is not None


def _segment(segment_id: int, words: Sequence[TimedWord]) -> Segment:
    """Return the Segment with this id made of words (at least one)."""
    items = [
        Word(
            text=w.text.strip(),
            start=round(w.start, DECIMALS),
            end=round(w.end, DECIMALS),
            speaker=SPEAKER,
            prob=round(w.prob, DECIMALS),
            approximate=w.approximate,
        )
        for w in words
    ]
    return Segment(
        id=segment_id,
        start=items[0].start,
        end=items[-1].end,
        text=" ".join("".join(w.text for w in words).split()),
        words=items,
        speaker=SPEAKER,
    )
