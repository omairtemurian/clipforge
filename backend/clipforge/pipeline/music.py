"""Background music (SPEC-v2 3.5): the bundled library and how a music
item sounds in a render.

The library is the CC0 loops in assets/music (BUNDLED_TRACKS, with the
license and attribution that assets/music/LICENSES.md gives); the owner can
add music files to the media library as well. A music item's file loops
for as long as the item lasts (LOOP_ARGS), at its volume, fading in and
out (music_filters), and with duck, it dips under the clip's speech:
sidechaincompress lowers the music while the clip's own sound, its key,
is louder than DUCK_THRESHOLD, and lets it back up in the gaps.
"""

from dataclasses import dataclass
from pathlib import Path

from clipforge.models import MusicProps

MUSIC_DIR = Path(__file__).resolve().parents[3] / "assets" / "music"
MUSIC_LICENSE = "CC0-1.0"
LOOP_ARGS = ["-stream_loop", "-1"]
# Ducking: while the key is over -40 dBFS RMS (speech; a pause's room noise
# is under it) the music is compressed 4:1, so quiet speech at -28 dBFS RMS
# dips it by about 10 dB, loudness-normalized speech (-16 dBFS) by about
# 18 dB. The music falls in 20 ms and comes back over 400 ms.
DUCK_THRESHOLD = 0.01
DUCK_RATIO = 4
DUCK_ATTACK_MS = 20
DUCK_RELEASE_MS = 400


@dataclass(frozen=True)
class BundledTrack:
    """A loop of assets/music: its file name, title and mood tags."""

    file: str
    title: str
    tags: tuple[str, ...]

    @property
    def attribution(self) -> str:
        """The attribution the library shows (CC0 needs none)."""
        return f'"{self.title}" by ClipForge, {MUSIC_LICENSE} (assets/music)'


BUNDLED_TRACKS: tuple[BundledTrack, ...] = (
    BundledTrack("bright_steps.flac", "Bright Steps", ("upbeat", "happy", "pop")),
    BundledTrack("slow_tide.flac", "Slow Tide", ("calm", "ambient", "soft")),
    BundledTrack(
        "night_drive.flac", "Night Drive", ("dramatic", "electronic", "driving")
    ),
    BundledTrack("paper_lanterns.flac", "Paper Lanterns", ("chill", "lofi", "relaxed")),
)


def bundled_track(path: Path | str) -> BundledTrack | None:
    """Return the bundled track whose file is named like path, or None."""
    name = Path(path).name
    return next((track for track in BUNDLED_TRACKS if track.file == name), None)


def music_filters(props: MusicProps, length: float) -> str:
    """Return the filters that set a music item of length seconds to its
    volume and fade it in from its start and out to its end (times in the
    item's own seconds, before it is delayed to its start); each fade is
    at most the item's length."""
    filters = [f"volume=volume={props.volume:g}"]
    fade_in, fade_out = min(props.fade_in, length), min(props.fade_out, length)
    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0:
        filters.append(f"afade=t=out:st={length - fade_out:.3f}:d={fade_out:.3f}")
    return ",".join(filters)


def duck_filter() -> str:
    """Return the filter that ducks its first input (the music, in the
    rendered clip's time) while its second (the clip's sound) is loud."""
    return (
        f"sidechaincompress=threshold={DUCK_THRESHOLD:g}:ratio={DUCK_RATIO:g}"
        f":attack={DUCK_ATTACK_MS:g}:release={DUCK_RELEASE_MS:g}"
    )
