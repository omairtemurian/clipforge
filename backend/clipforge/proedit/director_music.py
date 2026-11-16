"""The music of a rule-based Pro Edit plan (SPEC-v3 3.4, 3.5): the bed the
plan plays and its beat grid in seconds of the clip, and the choice of a bed
by a preset's moods and BPM range.

The Director itself does no I/O: the caller reads the grid of the chosen
music (beats.music_grid) and passes a MusicChoice. Without one a plan has no
bed and nothing is placed on beats.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from clipforge.pipeline.music import BUNDLED_TRACKS
from clipforge.proedit.beats import MusicGrid
from clipforge.proedit.preset_defs import MusicSpec

# Score of a candidate: BPM within the preset's range, unknown, or outside.
BPM_IN_RANGE = 2
BPM_UNKNOWN = 0
BPM_OUTSIDE = -1


@dataclass(frozen=True)
class MusicChoice:
    """The bed: asset (a library asset id or a bundled track's name), its
    beat grid in music seconds, and offset, the music second at clip 0."""

    asset: str
    grid: MusicGrid
    offset: float = 0.0

    def _in_clip(self, times: Sequence[float], duration: float) -> tuple[float, ...]:
        shifted = (t - self.offset for t in times)
        return tuple(t for t in shifted if 0 <= t < duration)

    def beats(self, duration: float) -> tuple[float, ...]:
        """The beats within a clip of duration seconds, in clip seconds."""
        return self._in_clip(self.grid.beats, duration)

    def downbeats(self, duration: float) -> tuple[float, ...]:
        """The downbeats within the clip, in clip seconds."""
        return self._in_clip(self.grid.downbeats, duration)


@dataclass(frozen=True)
class MusicCandidate:
    """A bed the owner may use: its asset, mood tags and BPM (None: not
    known)."""

    asset: str
    moods: tuple[str, ...]
    bpm: float | None = None


def bundled_candidates() -> list[MusicCandidate]:
    """The bundled music loops as candidates (their BPM is not tagged)."""
    return [MusicCandidate(Path(t.file).stem, t.tags) for t in BUNDLED_TRACKS]


def music_score(spec: MusicSpec, candidate: MusicCandidate) -> int:
    """How well candidate suits spec: the moods it shares plus the BPM
    score (BPM_IN_RANGE, BPM_UNKNOWN or BPM_OUTSIDE)."""
    moods = len(set(spec.moods) & set(candidate.moods))
    if candidate.bpm is None:
        return moods + BPM_UNKNOWN
    low, high = spec.bpm
    return moods + (BPM_IN_RANGE if low <= candidate.bpm <= high else BPM_OUTSIDE)


def pick_music(
    spec: MusicSpec, candidates: Sequence[MusicCandidate]
) -> MusicCandidate | None:
    """Return the candidate that suits spec best (the first asset name on a
    tie), or None when none shares a mood or has a BPM in range."""
    scored = [(music_score(spec, c), c) for c in candidates]
    suitable = [(score, c) for score, c in scored if score > 0]
    if not suitable:
        return None
    return min(suitable, key=lambda sc: (-sc[0], sc[1].asset))[1]
