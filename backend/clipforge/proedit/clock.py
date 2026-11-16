"""Source time -> clip time for a Pro Edit clip (SPEC-v3 3.1).

The EDL speaks in seconds of the rendered clip: the parts of the clip's
segments that play, less its cut ranges, in the order the render plays them
(sections.played_spans, whole frames at the render's frame rate). ClipClock
maps source seconds to those, so every signal of a clip is in the time its
EDL items use.
"""

from clipforge.models import Clip
from clipforge.pipeline.sections import played_spans

DECIMALS = 3


class ClipClock:
    """The rendered time of a clip's source moments."""

    def __init__(self, clip: Clip, fps: int) -> None:
        """Map the source seconds of clip as its render at fps plays them."""
        self.base = clip.start
        parts = played_spans(clip.start, clip.end, clip.segments, clip.cut_ranges, fps)
        self._parts: list[tuple[float, float, float]] = []
        elapsed = 0.0
        for start, end in parts:
            self._parts.append((start, end, elapsed))
            elapsed += end - start
        self.duration = round(elapsed, DECIMALS)

    def point(self, source_t: float) -> float | None:
        """Return the clip time of the source moment source_t, or None if
        the render does not play it."""
        rel = source_t - self.base
        for start, end, elapsed in self._parts:
            if start <= rel <= end:
                return round(elapsed + rel - start, DECIMALS)
        return None

    def spans(
        self, source_start: float, source_end: float
    ) -> list[tuple[float, float]]:
        """Return the (start, end) clip times of the parts of source_start to
        source_end that the render plays, in play order; [] if none."""
        low, high = source_start - self.base, source_end - self.base
        found = []
        for start, end, elapsed in self._parts:
            begin, finish = max(low, start), min(high, end)
            if begin < finish:
                found.append(
                    (
                        round(elapsed + begin - start, DECIMALS),
                        round(elapsed + finish - start, DECIMALS),
                    )
                )
        return found
