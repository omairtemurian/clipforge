"""A clip's cuts in whole frames (SPEC 6.10, 6.11): where a render cuts a
clip's cut ranges and the parts it keeps, and caption times after the cuts.

Cut ranges are seconds of the source within the clip. A render cuts whole
frames: with its fps, cut_spans moves each cut's edges to the nearest frame,
kept_spans gives the parts of the clip that the render keeps, and the
captions are retimed by the same cuts, so they stay in sync. After the
cuts, each moment of the clip comes earlier by the cut time before it
(output_ms): retime moves caption words so and leaves out those that cuts
remove whole.
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import replace
from itertools import chain

from clipforge.models import CutRange
from clipforge.pipeline.caption_lines import CaptionWord, to_ms

# A span of time in milliseconds: (start, end).
Span = tuple[int, int]


def frame_ms(time: int, fps: int) -> int:
    """Return the start of the frame nearest to time in a clip at fps frames a
    second, both in milliseconds from the clip's start."""
    return to_ms(math.floor(time * fps / 1000 + 0.5) / fps)


def cut_spans(
    start: float, end: float, cut_ranges: Iterable[CutRange], fps: int | None = None
) -> list[Span]:
    """Return the cut_ranges of the clip from start to end as spans in
    milliseconds from its start, in order.

    Spans are cut at the clip's edges. With fps, their edges inside the clip
    move to the nearest frame at fps frames a second (frame_ms), but not past
    its end. Spans that overlap or touch are merged and empty ones are left
    out.
    """
    first, length = to_ms(start), to_ms(end) - to_ms(start)

    def edge(time: int) -> int:
        """Return time, a span's edge, cut at the clip's edges and on a frame."""
        time = min(max(time - first, 0), length)
        if fps is None or time in (0, length):
            return time
        return min(frame_ms(time, fps), length)

    clipped = ((edge(to_ms(a)), edge(to_ms(b))) for a, b in cut_ranges)
    spans: list[Span] = []
    for span_start, span_end in sorted(clipped):
        if span_start >= span_end:
            continue
        if spans and span_start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], span_end))
        else:
            spans.append((span_start, span_end))
    return spans


def kept_spans(
    start: float, end: float, cut_ranges: Iterable[CutRange], fps: int
) -> list[tuple[float, float]]:
    """Return the parts of the clip from start to end that its cut_ranges
    leave, as (start, end) seconds from its start, in order; [] if the cuts
    leave nothing.

    The parts lie between the cuts of cut_spans with fps. Each of their edges
    but the clip's end is exactly the time of a frame (n / fps), so a part
    holds whole frames at fps frames a second and the audio of just those.
    """
    length = to_ms(end) - to_ms(start)
    edges = [0, *chain.from_iterable(cut_spans(start, end, cut_ranges, fps)), length]

    def seconds(time: int) -> float:
        """Return time, an edge in milliseconds, in seconds."""
        return time / 1000 if time == length else round(time * fps / 1000) / fps

    return [
        (seconds(begin), seconds(finish))
        for begin, finish in zip(edges[::2], edges[1::2], strict=True)
        if begin < finish
    ]


def output_ms(time: int, spans: Iterable[Span]) -> int:
    """Return when time, in milliseconds from a clip's start, comes in the
    clip after the cuts spans (cut_spans): earlier by the cut time before it.
    A time inside a cut comes where the cut was."""
    return time - sum(min(time, end) - start for start, end in spans if start < time)


def retime(words: Iterable[CaptionWord], spans: Sequence[Span]) -> list[CaptionWord]:
    """Return words, in milliseconds from a clip's start, at their times after
    the cuts spans (output_ms); words that a cut covers whole are left out."""
    return [
        replace(
            word, start=output_ms(word.start, spans), end=output_ms(word.end, spans)
        )
        for word in words
        if not any(start <= word.start and word.end <= end for start, end in spans)
    ]
