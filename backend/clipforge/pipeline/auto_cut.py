"""Auto cut (TASK-27): jump cuts that take the silences out of a clip.

With the project's auto_cut on (the default), a new clip's cut_ranges take
out each silence of more than auto_cut_min_pause_s seconds: a gap between
two spoken words of the clip (polish.spoken_pieces, so between caption
words, never inside one), or between the clip's start or end and its first
or last word. Each cut keeps PADDING_MS of the silence after the word
before it and before the word after it, so no word is clipped. A gap during
a laugh or applause event (signals.json) is not silent: the audience's
reaction stays, as in polish.

With clip anything on, auto cut takes nothing out: a moment without speech,
such as an action or a song, is what the clip is about.

This is separate from remove_fillers (polish.filler_cuts): either, both or
neither may be on, and save_clips merges their cuts (merge_ranges). The cuts
are ordinary cut ranges, which the editor shows and can restore one by one.
"""

from collections.abc import Iterable
from pathlib import Path

from clipforge.models import CutRange, ProcessingSettings, SignalEvent, Transcript
from clipforge.pipeline.caption_lines import to_ms
from clipforge.pipeline.polish import (
    REACTIONS,
    filler_cuts,
    load_polish_inputs,
    spoken_pieces,
)

# The silence that a cut keeps on each side, after and before a word.
PADDING_MS = 120


def auto_cuts(
    transcript: Transcript,
    events: Iterable[SignalEvent],
    start: float,
    end: float,
    min_pause_s: float,
) -> list[CutRange]:
    """Return the cut ranges that take the silences of more than min_pause_s
    seconds out of the clip from start to end (module docstring), in order,
    in seconds of the source to the millisecond.

    The clip's words are the spoken caption words of transcript that start
    in [start, end); a word that overlaps the next one leaves no gap.
    """
    first, last, longest = to_ms(start), to_ms(end), to_ms(min_pause_s)
    reactions = [(to_ms(e.start), to_ms(e.end)) for e in events if e.kind in REACTIONS]
    gaps: list[tuple[int, int]] = []
    spoken_end = first
    for piece in spoken_pieces(transcript):
        if first <= piece.start < last:
            gaps.append((spoken_end, piece.start))
            spoken_end = max(spoken_end, piece.end)
    gaps.append((spoken_end, last))
    cuts: list[CutRange] = []
    for gap_start, gap_end in gaps:
        reacted = any(a < gap_end and b > gap_start for a, b in reactions)
        if gap_end - gap_start > longest and not reacted:
            cut_start, cut_end = gap_start + PADDING_MS, gap_end - PADDING_MS
            if cut_start < cut_end:
                cuts.append((cut_start / 1000, cut_end / 1000))
    return cuts


def merge_ranges(ranges: Iterable[CutRange]) -> list[CutRange]:
    """Return ranges sorted by start, with those that overlap or touch merged
    into one."""
    merged: list[CutRange] = []
    for range_start, range_end in sorted(ranges):
        if merged and range_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], range_end))
        else:
            merged.append((range_start, range_end))
    return merged


def new_clip_cuts(
    job_dir: Path,
    spans: Iterable[tuple[float, float]],
    processing: ProcessingSettings,
) -> list[list[CutRange]]:
    """Return the cut ranges of new clips from start to end of spans, in
    order: their filler cuts (polish.filler_cuts) with remove_fillers on and
    their auto cuts with auto_cut on and clip_anything off, merged
    (merge_ranges).

    job_dir's transcript.json and signals.json are read only if either is on
    (and there are spans); raises StepError if one of them is missing or not valid.
    """
    spans = list(spans)
    auto_cut = processing.auto_cut and not processing.clip_anything
    if not spans or not (processing.remove_fillers or auto_cut):
        return [[] for _ in spans]
    transcript, events = load_polish_inputs(job_dir)
    result = []
    for start, end in spans:
        cuts: list[CutRange] = []
        if processing.remove_fillers:
            cuts += filler_cuts(transcript, events, start, end)
        if auto_cut:
            pause = processing.auto_cut_min_pause_s
            cuts += auto_cuts(transcript, events, start, end, pause)
        result.append(merge_ranges(cuts))
    return result
