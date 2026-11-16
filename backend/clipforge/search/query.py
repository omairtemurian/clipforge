"""The words of a library search: turn what the user typed into an FTS5
query, find the matches in a segment's text and the moment of its first
matching word.

Everything typed is searched as words, never as FTS5 syntax: each word is
quoted (so AND, OR, NOT, "-" and ":" are only text), a "quoted phrase" must
appear as written, and the last word, if it is not a phrase, also matches
longer words (a search as you type). Case and accents do not matter.
"""

import re
import unicodedata
from dataclasses import dataclass

from clipforge.models import SearchHighlight, Segment

# What highlight() puts around a match: control characters that no
# transcript holds.
MARK_START = "\x02"
MARK_END = "\x03"

_TERM = re.compile(r'"([^"]*)"|(\w+)')
_WORD = re.compile(r"\w+")


class SearchQueryError(ValueError):
    """What the user typed has no word to search for."""


@dataclass(frozen=True)
class Query:
    """A parsed search: match is the FTS5 MATCH expression; words are the
    folded words of the query and prefix the folded last word that also
    matches longer words (None if none does)."""

    match: str
    words: frozenset[str]
    prefix: str | None


def fold(text: str) -> str:
    """Return text in lower case without accents: "Café" -> "cafe"."""
    plain = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return plain.casefold()


def parse_query(text: str) -> Query:
    """Return the search for what the user typed. Raises SearchQueryError if
    it holds no word."""
    parts: list[str] = []
    words: set[str] = set()
    prefix: str | None = None
    found = list(_TERM.finditer(text))
    for index, found_term in enumerate(found):
        phrase, word = found_term.groups()
        tokens = _WORD.findall(phrase if word is None else word)
        if not tokens:
            continue
        words.update(fold(token) for token in tokens)
        quoted = '"' + " ".join(tokens) + '"'
        if word is not None and index == len(found) - 1:
            prefix = fold(word)
            quoted += "*"
        parts.append(quoted)
    if not parts:
        raise SearchQueryError("type a word or phrase to search for")
    return Query(" ".join(parts), frozenset(words), prefix)


def split_highlights(marked: str) -> tuple[str, list[SearchHighlight]]:
    """Return the text of marked, FTS5's highlight() output, without the
    marks, and where the marks were."""
    text: list[str] = []
    spans: list[SearchHighlight] = []
    start = 0
    for char in marked:
        if char == MARK_START:
            start = len(text)
        elif char == MARK_END:
            spans.append(SearchHighlight(start=start, end=len(text)))
        else:
            text.append(char)
    return "".join(text), spans


def moment_time(segment: Segment, query: Query) -> float:
    """Return the second of the video where the first word of segment that
    matches query is said; the segment's start if no word does."""
    for word in segment.words:
        for token in _WORD.findall(fold(word.text)):
            if token in query.words or (
                query.prefix is not None and token.startswith(query.prefix)
            ):
                return word.start
    return segment.start
