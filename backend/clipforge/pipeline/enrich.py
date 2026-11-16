"""Enrich step (SPEC 6.4): the transcript as the LLM reads it -> enriched.txt.

enriched.txt has one line per transcript segment of the job's timeframe:
"[mm:ss.s-mm:ss.s] S0: text", the segment's start and end rounded to 0.1 s,
its speaker and its text. The laugh, applause and scene-cut events of
signals.json are inserted into the text at their start times as markers:
"[LAUGH 2.1s 0.85]" and "[APPLAUSE 3.0s 0.70]" give an event's duration in
seconds and its intensity, and "[SCENE CUT]" marks a cut. A marker follows
the last piece of text that starts before its event, so a laugh after a
punchline ends the punchline's line. Silences and energy peaks get no
marker; score and snap read them from signals.json. Curate reads the lines
back with parse_line.
"""

import logging
import re
from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from clipforge.models import (
    Segment,
    SignalEvent,
    SignalKind,
    SignalList,
    SourceMeta,
    Transcript,
    Word,
)
from clipforge.pipeline.step import (
    ENRICHED,
    SIGNALS,
    TRANSCRIPT,
    StepSettings,
    is_done,
    load_json,
    load_meta,
    write_text,
)

logger = logging.getLogger(__name__)

# The name in the marker of each kind of event that enriched.txt shows.
MARKER_NAMES: dict[SignalKind, str] = {
    "laugh": "LAUGH",
    "applause": "APPLAUSE",
    "scene_cut": "SCENE CUT",
}
# The start of a line, "[mm:ss.s-", as timestamp writes it.
LINE_START = re.compile(r"\[(\d{2,}):([0-5]\d\.\d)-")


@dataclass(frozen=True, slots=True)
class PromptLine:
    """A transcript line as the LLM reads it; start is in source seconds."""

    start: float
    text: str


def timestamp(seconds: float) -> str:
    """Format seconds as mm:ss.s, rounded to 0.1 s: 65.5 -> "01:05.5".

    Minutes go past 59 for long videos: 3725 -> "62:05.0".
    """
    minutes, tenths = divmod(round(seconds * 10), 600)
    return f"{minutes:02d}:{tenths / 10:04.1f}"


def parse_line(text: str) -> PromptLine:
    """Return the PromptLine of a line of enriched.txt.

    Its start is the line's first time in seconds: "[01:05.5-01:09.0] S0:
    text" starts at 65.5, the segment's start rounded to 0.1 s. Raises
    ValueError if text does not start with "[mm:ss.s-".
    """
    match = LINE_START.match(text)
    if match is None:
        raise ValueError(f'{text[:40]!r} does not start with "[mm:ss.s-"')
    minutes, seconds = match.groups()
    return PromptLine(int(minutes) * 60 + float(seconds), text)


def marker(event: SignalEvent) -> str:
    """Return the marker of a laugh, applause or scene-cut event.

    A laugh or applause shows its duration in seconds with 1 decimal and its
    intensity with 2: "[LAUGH 2.1s 0.85]"; a scene cut is "[SCENE CUT]".
    Raises KeyError for a kind that has no marker (silence, energy_peak).
    """
    name = MARKER_NAMES[event.kind]
    if event.kind == "scene_cut":
        return f"[{name}]"
    return f"[{name} {event.end - event.start:.1f}s {event.intensity:.2f}]"


def piece_words(segment: Segment) -> list[list[Word]] | None:
    """Return the words of each piece of segment's text between whitespace.

    Whisper words without a leading space, such as "-five" in "twenty-five",
    belong to the piece of the word before them; words without text belong
    to none. Returns None if the words do not spell the pieces, one after
    the other, or if the segment has text but no words.
    """
    words = [word for word in segment.words if word.text.strip()]
    groups: list[list[Word]] = []
    used = 0
    for piece in segment.text.split():
        group: list[Word] = []
        spelled = ""
        while used < len(words) and len(spelled) < len(piece):
            group.append(words[used])
            spelled += words[used].text.strip()
            used += 1
        if spelled != piece:
            return None
        groups.append(group)
    return groups if used == len(words) else None


def text_pieces(segment: Segment) -> list[tuple[float, str]]:
    """Return the pieces of segment's text between whitespace, with start times.

    A piece starts when the first word in it starts (piece_words). If the
    words do not spell the text, or the segment has none, the whole text is
    one piece from the segment's start. A segment without text has no
    pieces.
    """
    pieces = segment.text.split()
    groups = piece_words(segment)
    if groups is None:
        return [(segment.start, " ".join(pieces))] if pieces else []
    return [
        (group[0].start, piece) for group, piece in zip(groups, pieces, strict=True)
    ]


def enriched_lines(
    segments: Iterable[Segment], events: Iterable[SignalEvent]
) -> list[PromptLine]:
    """Return the enriched.txt lines of segments, with the markers of events.

    Segments and their words are in time order, as transcribe writes them;
    a segment without text has no line. The marker of a laugh, applause or
    scene-cut event goes right after the last piece of text (text_pieces)
    that starts before the event; if none does, it opens the first line.
    Markers at one place are in order of start, then kind. Without lines,
    the markers have no place and are left out.
    """
    lines = [(seg, pieces) for seg in segments if (pieces := text_pieces(seg))]
    starts = [start for _, pieces in lines for start, _ in pieces]
    # after[k]: the markers that follow the first k pieces of all lines.
    after: list[list[str]] = [[] for _ in range(len(starts) + 1)]
    for event in sorted(events, key=lambda event: (event.start, event.kind)):
        if event.kind in MARKER_NAMES:
            after[bisect_left(starts, event.start)].append(marker(event))

    result: list[PromptLine] = []
    placed = 0
    for segment, pieces in lines:
        parts = list(after[0]) if placed == 0 else []
        for _, piece in pieces:
            placed += 1
            parts += [piece, *after[placed]]
        span = f"{timestamp(segment.start)}-{timestamp(segment.end)}"
        text = " ".join(parts)
        result.append(PromptLine(segment.start, f"[{span}] {segment.speaker}: {text}"))
    return result


def timeframe_segments(transcript: Transcript, meta: SourceMeta) -> list[Segment]:
    """Return the segments of transcript that start in meta's timeframe.

    They are the speech that enriched.txt shows the LLM, in time order.
    """
    start, end = meta.timeframe_start, meta.timeframe_end
    return [segment for segment in transcript.segments if start <= segment.start < end]


def run(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
    """Write the job's transcript with its event markers to enriched.txt.

    Reads meta.json (ingest), transcript.json (transcribe) and signals.json
    (signals), and uses the segments and events that start in the
    timeframe. Skips the work if enriched.txt exists, unless force. Raises
    StepError if an input is missing or not valid.
    """
    output = job_dir / ENRICHED
    if is_done(output, force=force):
        logger.info("%s exists; skipping enrich", output)
        settings.report_progress(1.0)
        return output
    output.unlink(missing_ok=True)

    meta = load_meta(job_dir)
    transcript = load_json(job_dir / TRANSCRIPT, Transcript, "transcribe")
    signals = load_json(job_dir / SIGNALS, SignalList, "signals").root
    start, end = meta.timeframe_start, meta.timeframe_end
    events = [event for event in signals if start <= event.start < end]
    lines = enriched_lines(timeframe_segments(transcript, meta), events)
    write_text(output, "".join(f"{line.text}\n" for line in lines))
    settings.report_progress(1.0)
    if lines:
        markers = sum(event.kind in MARKER_NAMES for event in events)
        logger.info("wrote %d lines, %d markers to %s", len(lines), markers, output)
    else:
        logger.warning("no speech in %.1fs-%.1fs; %s is empty", start, end, output)
    return output
