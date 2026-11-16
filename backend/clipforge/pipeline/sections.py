"""A clip's sections as its render plays them (SPEC-v2 3.5 section ops).

A clip plays its segments (sections) in their order. The sections never
overlap, but may leave gaps between them in the source and come in any
order. The render reads the source from the clip's start (its earliest
section's start) to its end (its latest section's end): the gaps between
the sections are cut like the clip's cut ranges (with_gaps), and the parts
that are left play section by section, in the sections' order
(in_play_order). Caption words, retimed by those cuts in time order, are
moved to where their part plays (reorder_words).

With one section, or sections in time order, nothing moves: a clip plays
as v1 rendered it.
"""

import math
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import replace
from itertools import chain, pairwise

from clipforge.models import Clip, CutRange, SourceSpan
from clipforge.pipeline.caption_lines import CaptionWord, to_ms
from clipforge.pipeline.frame_cuts import cut_spans, kept_spans, retime

Part = tuple[float, float]


def section_gaps(segments: Iterable[SourceSpan]) -> list[CutRange]:
    """Return the parts of the source between segments, in time order: from
    each one's end to the start of the next one in the source."""
    return [
        (before_end, after_start)
        for (_, before_end), (after_start, _) in pairwise(sorted(segments))
        if before_end < after_start
    ]


def fit_cuts(
    cut_ranges: Iterable[CutRange], segments: Sequence[SourceSpan]
) -> list[CutRange]:
    """Return the parts of cut_ranges inside segments, in order: a cut over
    a section's edge is cut there, one outside every section is dropped."""
    fitted = {
        (max(cut_start, start), min(cut_end, end))
        for cut_start, cut_end in cut_ranges
        for start, end in segments
        if max(cut_start, start) < min(cut_end, end)
    }
    return sorted(fitted)


def with_gaps(
    cut_ranges: Iterable[CutRange], segments: Iterable[SourceSpan]
) -> list[CutRange]:
    """Return cut_ranges with the gaps between segments (section_gaps), in
    order: everything the render leaves out of the clip's span."""
    return sorted([*cut_ranges, *section_gaps(segments)])


def played_spans(
    start: float,
    end: float,
    segments: Sequence[SourceSpan],
    cut_ranges: Iterable[CutRange],
    fps: int,
) -> list[Part]:
    """Return the parts of the clip from start to end that plays segments,
    without cut_ranges: (start, end) seconds from start, in the order the
    render plays them; [] if nothing is left.

    The gaps between segments are cut too (with_gaps), in whole frames as
    kept_spans cuts; then the parts play section by section
    (in_play_order). With one segment from start to end, these are
    kept_spans.
    """
    kept = kept_spans(start, end, with_gaps(cut_ranges, segments), fps)
    return in_play_order(kept, start, end, segments, fps)


def played_words(
    words: Iterable[CaptionWord], clip: Clip, fps: int
) -> list[CaptionWord]:
    """Return words of clip, in milliseconds from its start, at their times
    in its render at fps: retimed by its cuts and the gaps between its
    segments (cut_spans), then moved with their parts into the segments'
    order (reorder_words)."""
    cuts = with_gaps(clip.cut_ranges, clip.segments)
    words = retime(words, cut_spans(clip.start, clip.end, cuts, fps))
    played = played_spans(clip.start, clip.end, clip.segments, clip.cut_ranges, fps)
    return reorder_words(words, played)


def in_play_order(
    kept: Sequence[Part],
    start: float,
    end: float,
    segments: Sequence[SourceSpan],
    fps: int,
) -> list[Part]:
    """Return the parts kept, (start, end) seconds from start in time order
    (frame_cuts.kept_spans of the clip from start to end, without with_gaps),
    split at the sections' edges and in the order of segments: each
    section's parts, in time order, then the next section's
    (section_parts, flattened)."""
    return list(chain.from_iterable(section_parts(kept, start, end, segments, fps)))


def section_parts(
    kept: Sequence[Part],
    start: float,
    end: float,
    segments: Sequence[SourceSpan],
    fps: int,
) -> list[list[Part]]:
    """Return, for each of segments in order, the parts of kept (as
    in_play_order takes them) inside it, in time order: the cuts between a
    section's parts are its jump cuts.

    The sections' edges fall on the frames that kept's cut edges do, so a
    section's parts are exactly the ones kept inside it.
    """
    length = to_ms(end) - to_ms(start)
    by_section: list[list[Part]] = []
    for seg_start, seg_end in segments:
        low = _frame_s(to_ms(seg_start) - to_ms(start), length, fps)
        high = _frame_s(to_ms(seg_end) - to_ms(start), length, fps)
        by_section.append(
            [
                (max(begin, low), min(finish, high))
                for begin, finish in kept
                if max(begin, low) < min(finish, high)
            ]
        )
    return by_section


def reorder_words(
    words: Iterable[CaptionWord], played: Sequence[Part]
) -> list[CaptionWord]:
    """Return words, timed in milliseconds of the clip after its cuts in
    time order (frame_cuts.retime), at their times in the clip that plays the
    parts played in that order (in_play_order), sorted by start.

    A word moves with the part that its start is in, and ends by that
    part's end. With the parts in time order, words are returned as given.
    """
    words = list(words)
    if list(played) == sorted(played):
        return words
    lengths = [to_ms(end) - to_ms(begin) for begin, end in played]
    play_at = [sum(lengths[:index]) for index in range(len(played))]
    by_time = sorted(range(len(played)), key=lambda index: played[index])
    time_at: list[int] = []
    total = 0
    for index in by_time:
        time_at.append(total)
        total += lengths[index]
    moved = []
    for word in words:
        slot = max(bisect_right(time_at, word.start) - 1, 0)
        index = by_time[slot]
        shift = play_at[index] - time_at[slot]
        part_end = time_at[slot] + lengths[index]
        moved.append(
            replace(word, start=word.start + shift, end=min(word.end, part_end) + shift)
        )
    return sorted(moved, key=lambda word: (word.start, word.end))


def _frame_s(time: int, length: int, fps: int) -> float:
    """Return time, milliseconds from a clip's start, in seconds on the
    nearest frame at fps as frame_cuts.kept_spans places a cut's edge; the
    clip's edges (0 and length) stay where they are."""
    if time <= 0:
        return 0.0
    if time >= length:
        return length / 1000
    frame = math.floor(time * fps / 1000 + 0.5)
    if to_ms(frame / fps) >= length:
        return length / 1000
    return frame / fps
