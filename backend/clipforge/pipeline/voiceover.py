"""AI voiceover (SPEC-v2 3.5): text spoken by a local TTS voice
(engines/tts) on a clip's voiceover track, and the clip's own sound ducked
under it.

speak() writes the voice's WAV to {data_dir}/voiceover/<hash>.wav, named by
the voice, speed and text, so the same line is spoken only once. A
voiceover item plays that file (an "audio" asset tagged VOICEOVER_TAG) from
its start for as long as the speech lasts; its VoiceoverProps keep the text,
voice and speed, so it can be edited and spoken again.

While a voiceover item with duck plays, the clip's own sound is lowered to
DUCK_GAIN (-12 dB): duck_filter() is a volume filter evaluated per audio
frame whose gain ramps down over DUCK_RAMP_S before the item starts and
back up over DUCK_RAMP_S after it ends, in the rendered clip's time.
"""

import hashlib
import os
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from clipforge import config
from clipforge.config import Settings
from clipforge.engines.tts import synthesize, wav_seconds
from clipforge.models import Timeline, TrackItem, VoiceoverProps

VOICEOVER_DIRNAME = "voiceover"
VOICEOVER_TAG = "voiceover"
ITEM_PREFIX = "voiceover-"
DUCK_GAIN = 0.25
DUCK_RAMP_S = 0.15


@dataclass(frozen=True)
class Spoken:
    """A voiceover's WAV file and its length in seconds."""

    path: Path
    seconds: float


def voiceover_dir(cfg: Settings | None = None) -> Path:
    """Return the directory of the spoken voiceover files."""
    return (cfg or config.settings).data_dir / VOICEOVER_DIRNAME


def spoken_path(
    text: str, voice: str, speed: float, cfg: Settings | None = None
) -> Path:
    """Return the file that text spoken by voice at speed is kept in."""
    key = f"{voice}\n{speed:.4f}\n{text}".encode()
    return voiceover_dir(cfg) / f"{hashlib.sha256(key).hexdigest()[:32]}.wav"


def speak(
    text: str, voice: str, speed: float = 1.0, cfg: Settings | None = None
) -> Spoken:
    """Return the WAV of text spoken by voice at speed, speaking it now only
    if it was not spoken before. Raises like engines.tts.synthesize; a
    failed run leaves no file."""
    path = spoken_path(text, voice, speed, cfg)
    if path.is_file():
        return Spoken(path, wav_seconds(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=".speak-", suffix=".wav", dir=path.parent)
    os.close(handle)
    try:
        seconds = synthesize(text, voice, Path(temp), speed, cfg)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)
    return Spoken(path, seconds)


def next_item_id(tracks: Timeline) -> str:
    """Return an item id "voiceover-<n>" that no item of tracks has."""
    taken = {
        item.id for name in Timeline.model_fields for item in getattr(tracks, name)
    }
    number = 1
    while f"{ITEM_PREFIX}{number}" in taken:
        number += 1
    return f"{ITEM_PREFIX}{number}"


def voiceover_item(
    item_id: str, asset_id: int, start: float, seconds: float, props: VoiceoverProps
) -> TrackItem:
    """Return the voiceover item item_id that plays asset asset_id (seconds
    long) from start with props."""
    return TrackItem(
        id=item_id,
        kind="audio",
        asset_id=asset_id,
        start=round(start, 3),
        end=round(start + seconds, 3),
        props=props.model_dump(),
    )


def fit_problem(start: float, seconds: float, length: float) -> str | None:
    """Return why a voiceover of seconds from start does not fit a clip of
    length seconds, or None if it fits (to the millisecond)."""
    if round(start + seconds, 3) <= length + 0.001:
        return None
    left = max(length - start, 0.0)
    return (
        f"the voiceover lasts {seconds:.2f} s but the clip has only {left:.2f} s "
        f"left after {start:g} s; move it earlier or shorten the text"
    )


def duck_windows(
    items: Iterable[tuple[TrackItem, VoiceoverProps]],
) -> list[tuple[float, float]]:
    """Return the [start, end] seconds of the voiceover items that duck the
    clip's sound, in order."""
    return sorted((item.start, item.end) for item, props in items if props.duck)


def duck_filter(windows: Sequence[tuple[float, float]]) -> str:
    """Return the volume filter that lowers a sound to DUCK_GAIN in windows
    (rendered clip seconds, ramping over DUCK_RAMP_S on each side); "" if
    there are none."""
    if not windows:
        return ""
    ramps = [
        f"min(clip((t-{start - DUCK_RAMP_S:.3f})/{DUCK_RAMP_S},0,1),"
        f"clip(({end + DUCK_RAMP_S:.3f}-t)/{DUCK_RAMP_S},0,1))"
        for start, end in windows
    ]
    level = ramps[0]
    for ramp in ramps[1:]:
        level = f"max({level},{ramp})"
    return f"volume=volume='1-{1 - DUCK_GAIN:g}*{level}':eval=frame"
