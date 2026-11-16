"""Which words are said loudly (SPEC-v3 3.3: shake on loud words).

A word is loud when its RMS level (pipeline/loudness: dBFS of 25 ms frames
every 10 ms) is at least LOUD_OVER_DB above the median level of the clip's
words, so the threshold follows the recording's own volume. Words are
identified by their start in milliseconds (CaptionWord.start).
"""

from collections.abc import Sequence
from statistics import median

import numpy as np
import numpy.typing as npt

from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.loudness import Envelope, rms_db

# A word this many dB above the median word level is loud.
LOUD_OVER_DB = 6.0


def envelope_of(samples: npt.NDArray[np.float32]) -> Envelope:
    """Return the RMS envelope of samples, the 16 kHz mono sound (-1..1) of
    the rendered clip, whose first sample is at time 0."""
    return Envelope(0.0, rms_db(samples))


def word_levels(words: Sequence[CaptionWord], envelope: Envelope) -> dict[int, float]:
    """Return the level (dBFS) of each word that the envelope covers, by the
    word's start in milliseconds; words are in milliseconds of the clip and
    the envelope in its seconds."""
    levels: dict[int, float] = {}
    for word in words:
        level = envelope.level(word.start / 1000, word.end / 1000)
        if level is not None:
            levels[word.start] = level
    return levels


def loud_words(
    words: Sequence[CaptionWord],
    envelope: Envelope,
    over_db: float = LOUD_OVER_DB,
) -> frozenset[int]:
    """Return the starts (ms) of the words whose level is at least over_db
    above the median word level."""
    levels = word_levels(words, envelope)
    if not levels:
        return frozenset()
    typical = median(levels.values())
    return frozenset(
        start for start, level in levels.items() if level - typical >= over_db
    )
