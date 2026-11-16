"""Keyword search (SPEC-v2 3.2): clips around every place a search term is
said, found in the transcript without the LLM.

A term matches a run of consecutive transcript words whose letters and
digits equal those of its words, ignoring case and punctuation: "smart
fridges" matches "Smart fridges." but not "fridge". The words searched are
those of the segments that start in the timeframe, as the LLM would see
them. Each match gets a window of whole segments (sentences) around it:
from the segment it is said in, the segment before or after that keeps the
window shorter is added until the window is as long as the shortest clip
wanted, while it stays within the longest (keyword_goal). A segment too
long on its own is cut by words instead. Later matches inside a window join
it, and the next window starts after it, so windows do not overlap. Each
window is a candidate with neutral LLM scores; score and snap treat it like
the LLM's candidates.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from clipforge.candidate_rules import DEFAULT_HASHTAGS, length_range
from clipforge.config import Settings
from clipforge.models import (
    ClipCandidate,
    ProcessingSettings,
    Segment,
    SourceMeta,
    Transcript,
)
from clipforge.pipeline.enrich import timeframe_segments, timestamp
from clipforge.pipeline.snap import TAIL_S
from clipforge.pipeline.step import TRANSCRIPT, load_json

logger = logging.getLogger(__name__)

# The LLM scores of a keyword candidate: nothing rates it but the signals.
NEUTRAL_SCORE = 50
# The longest search term quoted in a title (titles are at most 70 chars).
TITLE_TERM_CHARS = 50
DECIMALS = 3

Span = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Match:
    """Where a search term is said: the words as said, from start to end
    seconds, in segments[first_segment..last_segment]."""

    term: str
    start: float
    end: float
    words: tuple[str, ...]
    first_segment: int
    last_segment: int
    # The index of the first matched word in its segment's words.
    first_word: int


@dataclass(slots=True)
class Window:
    """A clip from start to end seconds and the matches said in it."""

    start: float
    end: float
    matches: list[Match] = field(default_factory=list)


def normalize(text: str) -> str:
    """Return the letters and digits of text, lowercased (casefold)."""
    return "".join(char for char in text.casefold() if char.isalnum())


def bare(word: str) -> str:
    """Return word without the punctuation and spaces around it."""
    start, end = 0, len(word)
    while start < end and not word[start].isalnum():
        start += 1
    while end > start and not word[end - 1].isalnum():
        end -= 1
    return word[start:end]


def find_matches(segments: Sequence[Segment], terms: Sequence[str]) -> list[Match]:
    """Return every place a term is said in the words of segments, by start.

    A term matches consecutive words, also across segments, whose
    normalize()d text equals that of its words; words that are only
    punctuation are skipped. A term that has no letters or digits matches
    nothing. Matches that start together keep the order of terms.
    """
    said = [
        (normalize(word.text), word.text, index, position, word.start, word.end)
        for index, segment in enumerate(segments)
        for position, word in enumerate(segment.words)
        if normalize(word.text)
    ]
    matches = []
    for term in terms:
        tokens = [token for token in map(normalize, term.split()) if token]
        if not tokens:
            continue
        for at in range(len(said) - len(tokens) + 1):
            run = said[at : at + len(tokens)]
            if [entry[0] for entry in run] != tokens:
                continue
            first, last = run[0], run[-1]
            matches.append(
                Match(
                    term=term,
                    start=first[4],
                    end=last[5],
                    words=tuple(bare(entry[1]) for entry in run),
                    first_segment=first[2],
                    last_segment=last[2],
                    first_word=first[3],
                )
            )
    return sorted(matches, key=lambda match: match.start)


def keyword_goal(processing: ProcessingSettings, cfg: Settings) -> Span:
    """Return the (shortest, longest) seconds a keyword window aims for.

    It is the range of the first chosen length preset; for "auto" the usual
    clip of cfg.clip_min_s to cfg.clip_max_s. A range from 0 ("lt30",
    "0_60") aims for at least cfg.clip_min_s, so a match is not a clip of
    one word. The longest leaves room for the tail of TAIL_S that snap adds
    after the last word.
    """
    preset = processing.length_presets[0]
    if preset == "auto":
        low, high = float(cfg.clip_min_s), float(cfg.clip_max_s)
    else:
        low, high = length_range(preset, cfg, processing.custom_length)
    high = max(high - TAIL_S, low)
    return (low or min(float(cfg.clip_min_s), high)), high


def grow(units: Sequence[Span], first: int, last: int, floor: int, goal: Span) -> Span:
    """Return the span of units[first..last] grown to the goal's shortest.

    Each step adds the unit after or before (not before units[floor]) that
    gives the shorter span, the one after on a tie, as long as the span
    stays within the goal's longest; it stops when neither can be added.
    """
    low, high = goal

    def length(pair: tuple[int, int]) -> float:
        return round(units[pair[1]][1] - units[pair[0]][0], DECIMALS)

    while length((first, last)) < low:
        options = []
        if last + 1 < len(units):
            options.append((first, last + 1))
        if first - 1 >= floor:
            options.append((first - 1, last))
        fitting = [pair for pair in options if length(pair) <= high]
        if not fitting:
            break
        first, last = min(fitting, key=length)
    return units[first][0], units[last][1]


def match_window(
    match: Match, segments: Sequence[Segment], after: float, goal: Span
) -> Window:
    """Return the window around a match that starts no earlier than after
    (the end of the window before it), unless the match itself does.

    It is grown over whole segments, or over the words of the match's
    segment if that segment alone is longer than the goal's longest.
    """
    segment = segments[match.first_segment]
    if (
        match.first_segment == match.last_segment
        and segment.end - segment.start > goal[1]
    ):
        units = [(word.start, word.end) for word in segment.words]
        first = last = match.first_word
        last += len(match.words) - 1
        while last + 1 < len(units) and units[last][1] < match.end:
            last += 1
    else:
        units = [(s.start, s.end) for s in segments]
        first, last = match.first_segment, match.last_segment
    floor = next((i for i, unit in enumerate(units) if unit[0] >= after), first)
    start, end = grow(units, first, last, min(floor, first), goal)
    return Window(start, end, [match])


def candidate(window: Window, segments: Sequence[Segment]) -> ClipCandidate:
    """Return the clip candidate of a window: titled after its first match,
    described by the sentence it is said in, tagged with its terms, its
    matched words emphasized (each once, whatever its case), and neutral
    LLM scores."""
    first = window.matches[0]
    terms = list(dict.fromkeys(match.term for match in window.matches))
    words: dict[str, str] = {}
    for match in window.matches:
        for word in match.words:
            words.setdefault(word.casefold(), word)
    tags = [normalize(term) for term in terms] + list(DEFAULT_HASHTAGS)
    said = ", ".join(timestamp(match.start) for match in window.matches)
    quoted = ", ".join(f'"{term}"' for term in terms)
    return ClipCandidate(
        start=window.start,
        end=window.end,
        title=f'"{first.term[:TITLE_TERM_CHARS]}" at {timestamp(first.start)}',
        hook_text="",
        description=segments[first.first_segment].text.strip()[:300],
        hashtags=list(dict.fromkeys(tag for tag in tags if tag))[:8],
        emphasis_words=list(words.values()),
        reason=f"Keyword search: {quoted} said at {said}.",
        hook=NEUTRAL_SCORE,
        flow=NEUTRAL_SCORE,
        value=NEUTRAL_SCORE,
        trend=NEUTRAL_SCORE,
    )


def keyword_candidates(
    segments: Sequence[Segment], terms: Sequence[str], meta: SourceMeta, goal: Span
) -> list[ClipCandidate]:
    """Return a candidate for each window around the matches of terms in
    segments, in time order, clamped to the timeframe of meta."""
    windows: list[Window] = []
    for match in find_matches(segments, terms):
        current = windows[-1] if windows else None
        if current and current.start <= match.start and match.end <= current.end:
            current.matches.append(match)
            continue
        after = current.end if current else meta.timeframe_start
        windows.append(match_window(match, segments, after, goal))
    for window in windows:
        window.start = max(window.start, meta.timeframe_start)
        window.end = min(window.end, meta.timeframe_end)
    return [candidate(window, segments) for window in windows]


def search(
    job_dir: Path, meta: SourceMeta, processing: ProcessingSettings, cfg: Settings
) -> list[ClipCandidate]:
    """Return the keyword candidates of the job's transcript.json for
    processing.search_terms. Raises StepError if the transcript is missing
    or not valid."""
    transcript = load_json(job_dir / TRANSCRIPT, Transcript, "transcribe")
    segments = timeframe_segments(transcript, meta)
    found = keyword_candidates(
        segments, processing.search_terms, meta, keyword_goal(processing, cfg)
    )
    logger.info(
        "keyword search for %s: %d windows", processing.search_terms, len(found)
    )
    return found
