"""Caption cues: the sentences of a clip's captions that translation works
on (SPEC-v2 3.4, pipeline/caption_translate).

A cue is a run of caption words (caption_lines.clip_words) that ends after
a word that ends a sentence (SENTENCE_END), before a pause of more than
caption_lines.PAUSE_MS or a change of speaker, or at MAX_CUE_WORDS words.
It keeps the time of its words, in source seconds, and the speaker of its
first word.

A translated cue shows in that same time: its text is split at whitespace
and the time is shared out between the pieces by their length in
characters (spread_cue), so each piece is the active word for a while, as
transcript words are. A language written without spaces (Chinese,
Japanese) shows a cue as one piece.
"""

import re
from collections.abc import Iterable, Sequence

from clipforge.models import CaptionCue, CaptionTranslation
from clipforge.pipeline.caption_lines import PAUSE_MS, CaptionWord, to_ms

# A word that ends with one of these marks, maybe followed by closing quotes
# or brackets, ends a sentence (with the Arabic question mark and full-width
# marks).
SENTENCE_END = re.compile(r"[.!?…。！？؟][\"'”’)\]»]*$")
MAX_CUE_WORDS = 14


def cue_break(before: CaptionWord, after: CaptionWord) -> bool:
    """Return True if a cue ends between the words before and after: before
    ends a sentence, a pause of more than PAUSE_MS separates them, or their
    speakers differ."""
    return (
        bool(SENTENCE_END.search(before.text))
        or after.start - before.end > PAUSE_MS
        or after.speaker != before.speaker
    )


def group_cues(words: Iterable[CaptionWord]) -> list[list[CaptionWord]]:
    """Return words, in order, in cues of at most MAX_CUE_WORDS words that
    also end wherever cue_break finds a break."""
    cues: list[list[CaptionWord]] = []
    for word in words:
        cue = cues[-1] if cues else None
        if cue is None or len(cue) >= MAX_CUE_WORDS or cue_break(cue[-1], word):
            cues.append([word])
        else:
            cue.append(word)
    return cues


def source_cues(words: Sequence[CaptionWord], start: float) -> list[CaptionCue]:
    """Return the cues (group_cues) of words, the caption words of a clip
    that starts at start source seconds, with their words' text joined by
    spaces and their times in source seconds (to the millisecond)."""
    first = to_ms(start)
    return [
        CaptionCue(
            start=(first + cue[0].start) / 1000,
            end=(first + cue[-1].end) / 1000,
            text=" ".join(word.text for word in cue),
            speaker=cue[0].speaker,
        )
        for cue in group_cues(words)
    ]


def spread_cue(cue: CaptionCue) -> list[tuple[str, int, int]]:
    """Return the pieces of cue's text (split at whitespace) with the start
    and end in source milliseconds that each shows for: cue's time, shared
    out by the pieces' length in characters plus one for the space, with no
    gap between one piece and the next."""
    pieces = cue.text.split()
    begin = to_ms(cue.start)
    span = max(to_ms(cue.end) - begin, 0)
    weights = [len(piece) + 1 for piece in pieces]
    total, done = sum(weights), 0
    edges = [begin]
    for weight in weights:
        done += weight
        edges.append(begin + round(span * done / total))
    return [
        (piece, edges[index], edges[index + 1]) for index, piece in enumerate(pieces)
    ]


def translated_words(
    translation: CaptionTranslation, start: float, end: float
) -> list[CaptionWord]:
    """Return the caption words of translation's cues (spread_cue) that
    start in [start, end) source seconds, in milliseconds from start with
    ends cut at end, each with its cue's speaker."""
    first, last = to_ms(start), to_ms(end)
    return [
        CaptionWord(text, begin - first, min(finish, last) - first, speaker=cue.speaker)
        for cue in translation.cues
        for text, begin, finish in spread_cue(cue)
        if first <= begin < last
    ]
