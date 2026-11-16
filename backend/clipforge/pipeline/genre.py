"""The genre whose rules a job follows (SPEC 6.5).

It is the genre the user chose, or for "auto" the one the video's laughs
point to: comedy if more than COMEDY_LAUGHS_PER_MINUTE laugh events start
per minute of the job's timeframe, else podcast. Curate asks the LLM with
the genre's prompt (prompts/curate_<genre>.md); score and snap (SPEC 6.6,
6.7) treat comedy clips differently from the others.
"""

import logging
from collections.abc import Iterable
from pathlib import Path

from clipforge.models import (
    ContentGenre,
    ProcessingSettings,
    SignalEvent,
    SignalList,
    SourceMeta,
)
from clipforge.pipeline.step import SIGNALS, load_json

logger = logging.getLogger(__name__)

# "auto" is comedy above this many laugh events per minute, else podcast.
COMEDY_LAUGHS_PER_MINUTE = 1.0


def auto_genre(events: Iterable[SignalEvent], start: float, end: float) -> ContentGenre:
    """Return the genre that "auto" stands for in the seconds from start to end.

    It is "comedy" if more than COMEDY_LAUGHS_PER_MINUTE laugh events start
    in [start, end) per minute of it, else "podcast". Other kinds of events
    are not counted. start must be before end.
    """
    laughs = sum(1 for e in events if e.kind == "laugh" and start <= e.start < end)
    per_minute = laughs * 60 / (end - start)
    genre: ContentGenre = (
        "comedy" if per_minute > COMEDY_LAUGHS_PER_MINUTE else "podcast"
    )
    logger.info(
        "genre auto: %d laugh events in %.1fs-%.1fs (%.2f per minute) -> %s",
        laughs,
        start,
        end,
        per_minute,
        genre,
    )
    return genre


def job_genre(
    job_dir: Path, processing: ProcessingSettings, meta: SourceMeta
) -> ContentGenre:
    """Return the genre of a job: processing.genre, or for "auto" the
    auto_genre of the events in job_dir/signals.json over meta's timeframe.

    signals.json is read only for "auto". Raises StepError if it is needed
    and missing or not valid.
    """
    if processing.genre != "auto":
        return processing.genre
    events = load_json(job_dir / SIGNALS, SignalList, "signals").root
    return auto_genre(events, meta.timeframe_start, meta.timeframe_end)
