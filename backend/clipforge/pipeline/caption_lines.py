"""The words and lines of a clip's captions (SPEC 6.9).

A caption word is a piece of a transcript segment's text between whitespace
(enrich.piece_words), so Whisper's "twenty" and "-five" show as one word,
"twenty-five"; if a segment's words do not spell its text, each word shows
on its own. A clip's captions show the words that start in the clip, with
times in milliseconds from its start (a rendered clip starts at 0) and ends
cut at its end. The editor's caption_overrides replace the text of the
transcript words they match.

Words go into lines of at most max_words_per_line words; a line also ends
after a word that ends with punctuation (LINE_END) and before a pause of
more than PAUSE_MS. Lines go into pages, the lines shown at once, of at
most max_lines lines; a page ends before a pause of more than PAUSE_MS.
Emphasis words, the clip's emphasis_words, may be single words or phrases;
they and emoji keywords match words by key: the lowercase text without the
punctuation around it.
"""

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace

from clipforge.models import CaptionMark, Transcript, Word
from clipforge.pipeline.enrich import piece_words

# A pause longer than this between two words ends a caption line.
PAUSE_MS = 300
# A word that ends with one of these marks, maybe followed by closing quotes
# or brackets, ends a caption line.
LINE_END = re.compile(r"[.,!?;:…—][\"'”’)\]]*$")
# The non-word characters at the start and the end of a text.
EDGES = re.compile(r"^\W+|\W+$")


@dataclass(frozen=True, slots=True)
class CaptionWord:
    """A word as captions show it: its text, and its start and end in
    milliseconds from the clip's start. emphasis marks an emphasis word.

    speaker is the transcript's speaker of the word, color the color of that
    speaker's words (color_speakers). pinned is the emphasis that a mark set
    for the word whatever the clip's emphasis phrases say (None: they decide),
    emoji the emoji that a mark puts after the word ("": none; None: the
    template's emoji map decides), censor whether a mark censors the word
    (None: the clip's censor lists decide, pipeline/censor) and paint the
    color a mark gives the word, over its emphasis and speaker colors.
    """

    text: str
    start: int
    end: int
    emphasis: bool = False
    speaker: str = ""
    color: str | None = None
    pinned: bool | None = None
    emoji: str | None = None
    censor: bool | None = None
    paint: str | None = None


def to_ms(seconds: float) -> int:
    """Return seconds as a whole number of milliseconds: 10.36 -> 10360."""
    return round(seconds * 1000)


def word_key(text: str) -> str:
    """Return the key of a word: its text in lowercase without the punctuation
    around it. "Pizza." -> "pizza"; "don't" keeps its apostrophe."""
    return EDGES.sub("", text).lower()


def word_groups(transcript: Transcript) -> Iterator[list[Word]]:
    """Yield the transcript words of each caption word of transcript, in order:
    the words of a piece of a segment's text (enrich.piece_words), or each
    word on its own if the segment's words do not spell its text."""
    for segment in transcript.segments:
        groups = piece_words(segment)
        yield from ([word] for word in segment.words) if groups is None else groups


def resolve_marks(marks: Iterable[CaptionMark]) -> dict[int, CaptionMark]:
    """Return the marks by the start of their word in milliseconds; a "user"
    mark replaces an "ai" mark of the same word, otherwise the later mark
    wins."""
    resolved: dict[int, CaptionMark] = {}
    for mark in marks:
        key = to_ms(mark.start)
        if mark.source == "user" or resolved.get(key, mark).source == "ai":
            resolved[key] = mark
    return resolved


def clip_words(
    transcript: Transcript,
    start: float,
    end: float,
    overrides: Iterable[Word] = (),
    marks: Iterable[CaptionMark] = (),
) -> list[CaptionWord]:
    """Return the caption words of transcript that start in [start, end).

    They come in transcript order, with times in milliseconds from start and
    ends cut at end, and the speaker of their first transcript word. A word
    of overrides that has the start and end of a transcript word, to the
    millisecond, replaces that word's text; caption words left without text
    are left out. A mark (resolve_marks) of the word that starts at its time
    sets the word's pinned emphasis, emoji, censor and paint.
    """
    texts = {(to_ms(word.start), to_ms(word.end)): word.text for word in overrides}
    marked = resolve_marks(marks)
    first, last = to_ms(start), to_ms(end)
    result: list[CaptionWord] = []
    for group in word_groups(transcript):
        begin = to_ms(group[0].start)
        text = "".join(
            texts.get((to_ms(word.start), to_ms(word.end)), word.text).strip()
            for word in group
        )
        if first <= begin < last and text:
            finish = min(max(to_ms(group[-1].end), begin), last)
            mark = marked.get(begin)
            result.append(
                CaptionWord(
                    text,
                    begin - first,
                    finish - first,
                    speaker=group[0].speaker,
                    pinned=mark.emphasis if mark else None,
                    emoji=mark.emoji if mark else None,
                    censor=mark.censor if mark else None,
                    paint=mark.color if mark else None,
                )
            )
    return result


def color_speakers(
    words: Iterable[CaptionWord], colors: Mapping[str, str]
) -> list[CaptionWord]:
    """Return words with the color that colors gives their speaker; a word of
    a speaker that colors lacks keeps the template's colors."""
    return [replace(word, color=colors.get(word.speaker)) for word in words]


def mark_emphasis(
    words: Sequence[CaptionWord], phrases: Iterable[str]
) -> list[CaptionWord]:
    """Return words with emphasis on every run of them that one of phrases
    spells: the words' keys (word_key) are the phrase's words' keys, in order.

    Words that no phrase spells lose their emphasis, unless a mark pinned it
    (CaptionWord.pinned), which beats the phrases either way.
    """
    keys = [word_key(word.text) for word in words]
    marked = [False] * len(words)
    for phrase in phrases:
        wanted = [key for part in phrase.split() if (key := word_key(part))]
        if not wanted:
            continue
        for index in range(len(keys) - len(wanted) + 1):
            if keys[index : index + len(wanted)] == wanted:
                marked[index : index + len(wanted)] = [True] * len(wanted)
    return [
        replace(word, emphasis=flag if word.pinned is None else word.pinned)
        for word, flag in zip(words, marked, strict=True)
    ]


def line_break(before: CaptionWord, after: CaptionWord) -> bool:
    """Return True if a caption line ends between the words before and after:
    before ends with punctuation (LINE_END), or a pause of more than
    PAUSE_MS separates them."""
    return bool(LINE_END.search(before.text)) or after.start - before.end > PAUSE_MS


def group_lines(
    words: Iterable[CaptionWord], max_words: int
) -> list[list[CaptionWord]]:
    """Return words, in order, in caption lines of at most max_words words.

    A line also ends wherever line_break finds a break.
    """
    lines: list[list[CaptionWord]] = []
    for word in words:
        line = lines[-1] if lines else None
        if line is None or len(line) >= max_words or line_break(line[-1], word):
            lines.append([word])
        else:
            line.append(word)
    return lines


def group_pages(
    lines: Iterable[list[CaptionWord]], max_lines: int
) -> list[list[list[CaptionWord]]]:
    """Return lines, in order, in pages of at most max_lines lines.

    A page also ends before a line that starts more than PAUSE_MS after the
    page's last word ends.
    """
    pages: list[list[list[CaptionWord]]] = []
    for line in lines:
        page = pages[-1] if pages else None
        if (
            page is None
            or len(page) >= max_lines
            or line[0].start - page[-1][-1].end > PAUSE_MS
        ):
            pages.append([line])
        else:
            page.append(line)
    return pages


def active_end(word: CaptionWord, following: CaptionWord | None) -> int:
    """Return when word stops being the active (highlighted) word.

    That is when the following word starts, so the captions do not flicker
    between words, unless a pause of more than PAUSE_MS comes first: then
    it is word's end, as for the last word (following is None).
    """
    if following is not None and following.start - word.end <= PAUSE_MS:
        return following.start
    return word.end
