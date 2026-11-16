"""Polish (SPEC 6.10): a clip's filler cuts, and caption times after cuts.

With the project's remove_fillers on, a new clip's cut_ranges are its filler
cuts (filler_cuts), which rendering leaves out (SPEC 6.11):

- Fillers: the filler words of the transcript's language (clipforge.fillers;
  English: um, uh, erm, ah and their longer spellings), and its words that
  are fillers only alone ("like") when one stands alone between pauses:
  with silence of at least snap.PAUSE_S before and after it (no word before
  or after it counts as silence), so the "like" of "it watches me like a
  hawk" stays. Words are caption words (caption_lines.word_groups), so
  "um-hmm" is never cut in half, and match by key (fillers.filler_key).
- Pauses: once the fillers are gone, a gap of more than PAUSE_MS (or the
  pause threshold the editor sets) between
  two kept words of the clip, or between the clip's start or end and its
  first or last kept word. The cut keeps MARGIN_MS of silence on each side
  (less where a filler is), so a pause becomes 2 x MARGIN_MS long. A gap
  during a laugh or applause event (signals.json) is not a pause: the
  audience's reaction stays. Fillers in a gap that is not a pause are cut
  from the first one's start to the last one's end.

A cut never reaches into the kept words around its gap. Cut ranges are
seconds of the source within the clip, to the millisecond, in order.

cleanup_suggestions gives the same cuts with what each removes (fillers or
a pause), for the editor's speech cleanup review.

A render cuts whole frames (pipeline/frame_cuts) and plays the clip's
segments in their order (pipeline/sections); spoken_words and
rendered_words time the captions as it does, so they stay in sync.
rendered_words also masks the words the clip censors (pipeline/censor).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from clipforge.fillers import FillerWords, filler_key, filler_words
from clipforge.models import (
    CleanupKind,
    CleanupSuggestion,
    Clip,
    CutRange,
    SignalEvent,
    SignalList,
    Transcript,
)
from clipforge.pipeline.caption_cues import translated_words
from clipforge.pipeline.caption_lines import (
    CaptionWord,
    clip_words,
    to_ms,
    word_groups,
)
from clipforge.pipeline.censor import mask_words
from clipforge.pipeline.frame_cuts import Span
from clipforge.pipeline.sections import played_words
from clipforge.pipeline.snap import PAUSE_S
from clipforge.pipeline.step import SIGNALS, TRANSCRIPT, load_json

# The language whose filler words is_filler uses by default.
DEFAULT_LANGUAGE = "en"
# The silence before and after a filler that stands alone, at least.
LIKE_PAUSE_MS = to_ms(PAUSE_S)
# A gap between kept words longer than this is a pause, which is cut.
PAUSE_MS = 600
# The silence that a cut pause keeps after the word before it and before the
# word after it.
MARGIN_MS = 150
# The kinds of signal events whose gaps are not pauses.
REACTIONS = frozenset({"laugh", "applause"})


@dataclass(frozen=True, slots=True)
class Piece:
    """A caption word of a transcript: its key (fillers.filler_key), and its
    start and end in milliseconds of the source."""

    key: str
    start: int
    end: int


def spoken_pieces(transcript: Transcript) -> list[Piece]:
    """Return the caption words of transcript that have text, in order."""
    pieces = []
    for group in word_groups(transcript):
        text = "".join(word.text.strip() for word in group)
        if text:
            begin, finish = to_ms(group[0].start), to_ms(group[-1].end)
            pieces.append(Piece(filler_key(text), begin, finish))
    return pieces


def is_filler(
    pieces: Sequence[Piece], index: int, fillers: FillerWords | None = None
) -> bool:
    """Return True if pieces[index] is a filler of fillers (default: the
    English ones): its key is always a filler, or it is a filler alone with
    at least LIKE_PAUSE_MS of silence before and after it."""
    words = filler_words(DEFAULT_LANGUAGE) if fillers is None else fillers
    piece = pieces[index]
    if piece.key not in words.alone:
        return piece.key in words.always
    before = index == 0 or piece.start - pieces[index - 1].end >= LIKE_PAUSE_MS
    last = index == len(pieces) - 1
    return before and (last or pieces[index + 1].start - piece.end >= LIKE_PAUSE_MS)


def filler_cuts(
    transcript: Transcript, events: Iterable[SignalEvent], start: float, end: float
) -> list[CutRange]:
    """Return the cut ranges that take the fillers and pauses (module
    docstring) out of the clip from start to end, in order: the spans of
    its cleanup_suggestions."""
    suggestions = cleanup_suggestions(transcript, events, start, end)
    return [(suggestion.start, suggestion.end) for suggestion in suggestions]


def cleanup_suggestions(
    transcript: Transcript,
    events: Iterable[SignalEvent],
    start: float,
    end: float,
    fillers: FillerWords | None = None,
    pause_ms: int | None = PAUSE_MS,
) -> list[CleanupSuggestion]:
    """Return the cuts that take the fillers and pauses (module docstring)
    out of the clip from start to end, in order, each with what it removes.

    The clip's words are the caption words of transcript that start in
    [start, end); events are the job's signal events, whose laughs and
    applause keep the gaps they fall in. fillers are the filler words
    (default: those of the transcript's language, fillers.filler_words;
    fillers.NO_FILLERS cuts none), pause_ms the longest gap that is not a
    pause (None: no pause is cut).
    """
    if fillers is None:
        fillers = filler_words(transcript.language)
    first, last = to_ms(start), to_ms(end)
    reactions = [(to_ms(e.start), to_ms(e.end)) for e in events if e.kind in REACTIONS]
    pieces = spoken_pieces(transcript)
    kept_end = first
    found: list[Piece] = []
    suggestions: list[CleanupSuggestion] = []
    for index, piece in enumerate(pieces):
        if not first <= piece.start < last:
            continue
        if is_filler(pieces, index, fillers):
            found.append(piece)
            continue
        suggestions += gap_cut((kept_end, piece.start), found, reactions, pause_ms)
        kept_end, found = piece.end, []
    return suggestions + gap_cut((kept_end, last), found, reactions, pause_ms)


def gap_cut(
    gap: Span,
    fillers: Sequence[Piece],
    reactions: Sequence[Span],
    pause_ms: int | None = PAUSE_MS,
) -> list[CleanupSuggestion]:
    """Return the cut, if any, of gap, the time between two kept words (or a
    clip's edge), with fillers in it, as a list of no or one suggestion.

    A pause (a gap of more than pause_ms that no reaction overlaps; None:
    never a pause) is cut from MARGIN_MS after its start to MARGIN_MS before
    its end, widened to take in the fillers; otherwise only the fillers are
    cut. The cut stays within gap. It is a "filler" cut, whose text is the
    fillers' keys, if there are fillers, else a "pause".
    """
    gap_start, gap_end = gap
    starts = [filler.start for filler in fillers]
    ends = [filler.end for filler in fillers]
    reacted = any(
        r_start < gap_end and r_end > gap_start for r_start, r_end in reactions
    )
    if pause_ms is not None and gap_end - gap_start > pause_ms and not reacted:
        starts.append(gap_start + MARGIN_MS)
        ends.append(gap_end - MARGIN_MS)
    if not starts:
        return []
    cut_start, cut_end = max(min(starts), gap_start), min(max(ends), gap_end)
    if cut_start >= cut_end:
        return []
    text = " ".join(filler.key for filler in fillers)
    kind: CleanupKind = "filler" if fillers else "pause"
    return [
        CleanupSuggestion(
            start=cut_start / 1000, end=cut_end / 1000, kind=kind, text=text
        )
    ]


def load_filler_cuts(
    job_dir: Path, spans: Iterable[tuple[float, float]]
) -> list[list[CutRange]]:
    """Return the filler cuts (filler_cuts) of the clips from start to end of
    spans, in order, with job_dir's transcript.json and signals.json.

    Raises StepError if either file is missing or not valid.
    """
    transcript, events = load_polish_inputs(job_dir)
    return [filler_cuts(transcript, events, start, end) for start, end in spans]


def load_polish_inputs(job_dir: Path) -> tuple[Transcript, list[SignalEvent]]:
    """Return the transcript and the signal events of job_dir's
    transcript.json and signals.json; StepError if either is missing or not
    valid."""
    transcript = load_json(job_dir / TRANSCRIPT, Transcript, "transcribe")
    return transcript, load_json(job_dir / SIGNALS, SignalList, "signals").root


def spoken_words(transcript: Transcript, clip: Clip, fps: int) -> list[CaptionWord]:
    """Return the transcript's words in clip (caption_lines.clip_words with
    its caption_overrides and the word_marks of its caption_style), retimed
    by its cut_ranges and segments as the render cuts and plays them
    (sections.played_words with fps), in milliseconds from the clip's start: what
    the clip's sound says."""
    marks = clip.caption_style.word_marks or []
    words = clip_words(transcript, clip.start, clip.end, clip.caption_overrides, marks)
    return played_words(words, clip, fps)


def rendered_words(transcript: Transcript, clip: Clip, fps: int) -> list[CaptionWord]:
    """Return the caption words of clip as its render at fps frames a second
    shows them: its spoken_words, or the words of its caption_style's
    translation if it has one, retimed by its cut_ranges and segments as
    the render cuts and plays them (sections.played_words with fps), in
    milliseconds from the clip's start, with
    the words it censors masked (censor.mask_words, with the lists of the
    captions' language). Raises StepError if the custom censor list is
    needed and its file is not valid."""
    style = clip.caption_style
    if style.translation is None:
        words, language = spoken_words(transcript, clip, fps), transcript.language
    else:
        translated = translated_words(style.translation, clip.start, clip.end)
        words = played_words(translated, clip, fps)
        language = style.translation.language
    return mask_words(words, style.censor, language)
