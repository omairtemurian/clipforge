"""Snap step (SPEC 6.7): clips cut between words -> snapped.json.

The clips that score kept (scored.json) have the times the LLM gave, which
it read from enriched.txt rounded to 0.1 s, so they can fall inside a word.
Snap moves them onto the words of transcript.json that the LLM saw (the
segments that start in the timeframe):
- start: the start of the first word at or after start - START_LOOKBACK_S
  that opens a phrase, that is, begins a segment or follows a pause of at
  least PAUSE_S after the word before it. If no word that starts in the
  clip opens a phrase, the first word that starts in it is taken.
- end: the end of the last word that starts before end, plus a tail. For
  comedy it lasts until the laugh after that word ends, at most
  LAUGH_TAIL_MAX_S; for the other genres, and when no laugh follows the
  word, it is TAIL_S. A tail stops where the next word starts and at the
  end of the timeframe.
So no clip starts or ends inside a word. A clip in which no word starts
has no speech to cut and is dropped, unless the job clips anything: then it
keeps the LLM's times. The clips keep their order and scores
in snapped.json; the process job saves them as the project's clips.
"""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from clipforge.models import (
    ScoredCandidate,
    ScoredList,
    Segment,
    SignalEvent,
    SignalList,
    Transcript,
)
from clipforge.pipeline.enrich import timeframe_segments
from clipforge.pipeline.genre import job_genre
from clipforge.pipeline.step import (
    SCORED,
    SIGNALS,
    SNAPPED,
    TRANSCRIPT,
    StepSettings,
    is_done,
    load_json,
    load_meta,
    write_json,
)
from clipforge.pipeline.visuals import wanted

logger = logging.getLogger(__name__)

# A clip may start this long before the time the LLM gave.
START_LOOKBACK_S = 0.3
# A word that starts this long or longer after the word before it ends
# opens a phrase.
PAUSE_S = 0.35
# The tail after a clip's last word, and the longest tail a laugh gives.
TAIL_S = 0.3
LAUGH_TAIL_MAX_S = 1.5
# Times are compared, and snapped times rounded, to milliseconds.
DECIMALS = 3


@dataclass(frozen=True, slots=True)
class SpokenWord:
    """A transcript word: its start and end in seconds, and whether it opens
    a phrase, so that a clip may start with it."""

    start: float
    end: float
    opens: bool


def spoken_words(segments: Iterable[Segment]) -> list[SpokenWord]:
    """Return the words of segments, in order.

    A word opens a phrase if it is the first word of its segment, or if it
    starts PAUSE_S or more (to the millisecond) after the word before it
    ends.
    """
    words: list[SpokenWord] = []
    for segment in segments:
        for index, word in enumerate(segment.words):
            pause = not words or round(word.start - words[-1].end, DECIMALS) >= PAUSE_S
            words.append(SpokenWord(word.start, word.end, index == 0 or pause))
    return words


def start_word(start: float, end: float, words: Sequence[SpokenWord]) -> int | None:
    """Return the index of the word that the clip from start to end starts with.

    Of the words that start at or after start - START_LOOKBACK_S and before
    end, it is the first one that opens a phrase, or if none does, the first
    one. Returns None if no word starts there.
    """
    low = start - START_LOOKBACK_S
    inside = [
        index
        for index, word in enumerate(words)
        if round(word.start - low, DECIMALS) >= 0
        and round(end - word.start, DECIMALS) > 0
    ]
    if not inside:
        return None
    return next((index for index in inside if words[index].opens), inside[0])


def end_word(end: float, words: Sequence[SpokenWord]) -> int | None:
    """Return the index of the last word that starts before end, or None if
    no word does."""
    before = [
        index
        for index, word in enumerate(words)
        if round(end - word.start, DECIMALS) > 0
    ]
    return before[-1] if before else None


def laugh_end(after: float, events: Iterable[SignalEvent]) -> float | None:
    """Return when the laugh after the time after (seconds) ends.

    It is the latest end of the laugh events that end after it and start at
    most LAUGH_TAIL_MAX_S after it; None if there is none. Other kinds of
    events, applause too, do not count.
    """
    return max(
        (
            e.end
            for e in events
            if e.kind == "laugh"
            and round(e.end - after, DECIMALS) > 0
            and round(after + LAUGH_TAIL_MAX_S - e.start, DECIMALS) >= 0
        ),
        default=None,
    )


def snap_end(
    words: Sequence[SpokenWord],
    last: int,
    events: Iterable[SignalEvent],
    *,
    comedy: bool,
    limit: float,
) -> float:
    """Return the end of a clip whose last word is words[last].

    It is the word's end plus the tail: for comedy, until the laugh after
    the word ends (laugh_end), at most LAUGH_TAIL_MAX_S; else, or without
    such a laugh, TAIL_S. The tail stops where the next word starts and at
    limit (the end of the timeframe), but the word itself is never cut.
    """
    word_end = words[last].end
    tail_end = word_end + TAIL_S
    laugh = laugh_end(word_end, events) if comedy else None
    if laugh is not None:
        tail_end = min(laugh, word_end + LAUGH_TAIL_MAX_S)
    if last + 1 < len(words):
        tail_end = min(tail_end, words[last + 1].start)
    return round(max(word_end, min(tail_end, limit)), DECIMALS)


def snap_clip(
    clip: ScoredCandidate,
    words: Sequence[SpokenWord],
    events: Sequence[SignalEvent],
    *,
    comedy: bool,
    limit: float,
) -> ScoredCandidate | None:
    """Return clip with its start and end snapped onto words (SPEC 6.7).

    The start is that of start_word and the end that of snap_end for the
    last word that starts before the clip's end; limit is the end of the
    timeframe. Returns None if no word starts in the clip, which then has
    no speech to snap to.
    """
    first = start_word(clip.start, clip.end, words)
    last = end_word(clip.end, words)
    if first is None or last is None:
        return None
    start = round(words[first].start, DECIMALS)
    end = snap_end(words, last, events, comedy=comedy, limit=limit)
    return clip.model_copy(update={"start": start, "end": end})


def run(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
    """Write the clips that score kept, snapped onto words, to snapped.json.

    Reads meta.json (ingest), transcript.json (transcribe), signals.json
    (signals) and scored.json (score), and snaps each clip (snap_clip) to
    the words of the timeframe, with comedy tails if the job's genre
    (pipeline/genre) is comedy. The clips keep their order and scores; a
    clip without words is dropped with a warning, or kept as it is when the
    job clips anything (visuals.wanted). With clipping "captions_only" the
    one clip is the chosen timeframe, so it is kept as it is. Skips the work if
    snapped.json exists, unless force. Raises StepError if an input is
    missing or not valid.
    """
    output = job_dir / SNAPPED
    if is_done(output, force=force):
        logger.info("%s exists; skipping snap", output)
        settings.report_progress(1.0)
        return output
    output.unlink(missing_ok=True)

    meta = load_meta(job_dir)
    transcript = load_json(job_dir / TRANSCRIPT, Transcript, "transcribe")
    events = load_json(job_dir / SIGNALS, SignalList, "signals").root
    scored = load_json(job_dir / SCORED, ScoredList, "score").clips
    if settings.processing.clipping == "captions_only":
        logger.info("captions only: keeping the timeframe as the clip")
        write_json(output, ScoredList(clips=scored))
        settings.report_progress(1.0)
        return output
    comedy = job_genre(job_dir, settings.processing, meta) == "comedy"
    words = spoken_words(timeframe_segments(transcript, meta))
    keep_silent = wanted(settings)
    snapped: list[ScoredCandidate] = []
    for clip in scored:
        moved = snap_clip(clip, words, events, comedy=comedy, limit=meta.timeframe_end)
        if moved is None and keep_silent:
            logger.info(
                "kept %g-%gs without speech: %r", clip.start, clip.end, clip.title
            )
            snapped.append(clip)
            continue
        if moved is None:
            logger.warning(
                "dropped %g-%gs: no word starts in it: %r",
                clip.start,
                clip.end,
                clip.title,
            )
            continue
        logger.info(
            "snapped %g-%gs to %g-%gs: %r",
            clip.start,
            clip.end,
            moved.start,
            moved.end,
            clip.title,
        )
        snapped.append(moved)
    write_json(output, ScoredList(clips=snapped))
    settings.report_progress(1.0)
    return output
