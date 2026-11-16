"""Non-speech audio events (SPEC-v2 3.2): laughter, applause, cheering, music.

YAMNet scores 521 AudioSet classes. The classes that matter to curation are
named by their display names in the class map of the installed model
(Yamnet.class_index checks that the map has them, so a class map without one
is an error and no name is guessed). The signals step keeps each class's
score per second in audio_events.json (audio_track) and merges its active
frames into events in signals.json: laugh and applause as before, cheer and
music too. Scoring counts applause and cheers as energy
(signal_merge.CROWD_KINDS); music is stored for the curate prompt and search
and does not move a clip's score.
"""

from collections.abc import Sequence

from clipforge.models import AudioEventKind, AudioEventTrack
from clipforge.pipeline.signal_merge import ScoredSpan, per_second_scores

# The YAMNet class (its display name in the class map) of each audio event.
EVENT_CLASSES: dict[AudioEventKind, str] = {
    "laugh": "Laughter",
    "applause": "Applause",
    "cheer": "Cheering",
    "music": "Music",
}
# Scores and times are rounded to 3 decimals.
DECIMALS = 3


def audio_track(
    kind: AudioEventKind, frames: Sequence[ScoredSpan], start: float, end: float
) -> AudioEventTrack:
    """Return the per-second scores of kind in [start, end] s.

    frames are the scored spans of the kind's YAMNet class (the signals step's
    frame_spans); the track has one score per second from start.
    """
    return AudioEventTrack(
        kind=kind,
        start=round(start, DECIMALS),
        scores=[round(s, DECIMALS) for s in per_second_scores(frames, start, end)],
    )
