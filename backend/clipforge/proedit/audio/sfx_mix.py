"""The SFX of a Pro Edit render (SPEC-v3 3.3, 3.6): the sfx items played into
the clip's sound, frame-accurate, ducked under speech.

Each item's sound is read by an `amovie` source (no extra ffmpeg input) and
brought to SAMPLE_RATE. Its pitch (params.pitch_semitones) is varispeed:
`asetrate` relabels the samples at SAMPLE_RATE * 2^(semitones / 12) and
`aresample` brings them back, so a higher pitch also plays shorter. Then
by params.fit:
- stretch: `rubberband` (if the ffmpeg build has it; sample-exact) or
  else `atempo` (0.5 to 100 a filter, chained for slower; its WSOLA
  windows can blur the end by a few tens of milliseconds) makes the sound
  last the item, trimmed and padded to its length exactly;
- natural: the sound plays at its pitched length, cut at the item's end
  with a FADE_S fade so the cut does not click.
It is set to params.gain_db and delayed (`adelay`, in milliseconds to the
microsecond) to the item's start; every time is on the frame grid, so the
sound starts on its frame. The sounds are added up (`amix`, normalize=0)
into the SFX bus, which is lowered by SPEECH_DUCK_DB while the clip speaks
(the base's speech spans, ramping over DUCK_RAMP_S on each side; ramps
summed balanced so the expression never nests deep: envelope.py), muted
in the silences before drops, and the bus is added to the clip's sound,
which keeps its length.

The pitch shift is always asetrate/aresample, so a variant sounds the same
on every ffmpeg build; only the time stretch uses rubberband when present
(docs/decisions.md).
"""

import math
from collections.abc import Mapping, Sequence
from pathlib import Path

from clipforge.ffmpeg import filter_value
from clipforge.proedit.audio.envelope import (
    Span,
    dip_filter,
    gate_filter,
    merged_spans,
)
from clipforge.proedit.audio.sounds import (
    SoundItem,
    ffmpeg_has,
    find_sound,
    sfx_items,
    sound_seconds,
)
from clipforge.proedit.edl import SfxItem, TypedEdlItem

SAMPLE_RATE = 48000
TEMPO_MIN = 0.5
FADE_S = 0.01
SPEECH_DUCK_DB = 6.0
DUCK_RAMP_S = 0.05
MUTE_RAMP_S = 0.005
NO_SFX_FILTER = "anull"
RUBBERBAND = "rubberband"
SFX_BUS = "[sfx_bus]"


def pitch_rate(semitones: float) -> int:
    """Return the sample rate that asetrate relabels SAMPLE_RATE samples to
    for a pitch of semitones."""
    return round(SAMPLE_RATE * 2 ** (semitones / 12))


def pitched_seconds(seconds: float, semitones: float) -> float:
    """Return how long a sound of seconds plays at a pitch of semitones."""
    return seconds * SAMPLE_RATE / pitch_rate(semitones)


def tempo_filters(tempo: float, rubberband: bool = False) -> list[str]:
    """Return the filters that play a sound at tempo (its length divided by
    tempo): one rubberband filter if rubberband, else one atempo filter or
    a chain of atempo=0.5 for tempos below TEMPO_MIN; [] at tempo 1."""
    if math.isclose(tempo, 1.0, abs_tol=1e-9):
        return []
    if rubberband:
        return [f"{RUBBERBAND}=tempo={tempo:.6f}"]
    filters = []
    while tempo < TEMPO_MIN:
        filters.append(f"atempo={TEMPO_MIN:g}")
        tempo /= TEMPO_MIN
    return [*filters, f"atempo={tempo:.6f}"]


def played_seconds(item: SfxItem, seconds: float) -> float:
    """Return how long item's sound, seconds long, plays in the render."""
    length = item.t_end - item.t_start
    if item.params.fit == "stretch":
        return length
    return min(length, pitched_seconds(seconds, item.params.pitch_semitones))


def sound_filter(
    item: SfxItem, path: Path, seconds: float, label: str, rubberband: bool = False
) -> str:
    """Return the chain that plays item's sound path (seconds long) as the
    module docstring says (stretched by rubberband if rubberband), into
    label."""
    semitones = item.params.pitch_semitones
    length = item.t_end - item.t_start
    filters = [
        f"amovie=filename={filter_value(str(path.absolute()))}",
        f"aresample={SAMPLE_RATE}",
    ]
    if semitones:
        filters += [f"asetrate={pitch_rate(semitones)}", f"aresample={SAMPLE_RATE}"]
    pitched = pitched_seconds(seconds, semitones)
    if item.params.fit == "stretch":
        filters += tempo_filters(pitched / length, rubberband)
        filters += [f"atrim=duration={length:.6f}", f"apad=whole_dur={length:.6f}"]
    elif pitched > length:
        fade = min(FADE_S, length)
        filters += [
            f"atrim=duration={length:.6f}",
            f"afade=t=out:st={length - fade:.6f}:d={fade:.6f}",
        ]
    filters += [
        f"volume={item.params.gain_db:g}dB",
        f"adelay=delays={item.t_start * 1000:.3f}:all=1",
    ]
    return ",".join(filters) + label


def duck_filter(
    speech: Sequence[Span],
    items: Sequence[SoundItem],
    db: float = SPEECH_DUCK_DB,
) -> str:
    """Return the volume filter that lowers a sound by db in the speech
    spans (seconds) that items sound in, ramping over DUCK_RAMP_S on each
    side; "" if no item sounds over speech."""
    ramp = DUCK_RAMP_S
    spans = [
        (start, end)
        for start, end in merged_spans(speech, 2 * ramp)
        if any(i.t_start < end + ramp and start - ramp < i.t_end for i in items)
    ]
    return dip_filter(spans, db, ramp)


def audio_graph(
    items: Sequence[TypedEdlItem],
    speech: Sequence[tuple[float, float]],
    library: Mapping[str, Path],
    source: str,
    out: str,
    rubberband: bool | None = None,
    silences: Sequence[Span] = (),
) -> str:
    """Return the filters that mix the SFX items of items (their sounds
    found by sounds.find_sound in library: all must be, graph.undrawn) into
    the sound labelled source, into out; source passes through untouched
    when there are none. Stretches use rubberband if rubberband (by default
    if the configured ffmpeg has it). The SFX are muted in silences (the
    silences before drops; MUTE_RAMP_S fades inside their edges)."""
    sounds = sfx_items(items)
    if not sounds:
        return f"{source}{NO_SFX_FILTER}{out}"
    if rubberband is None:
        rubberband = ffmpeg_has(RUBBERBAND)
    parts, labels = [], []
    for item in sounds:
        path = find_sound(item.params.asset, library)
        if path is None:
            raise ValueError(f"item {item.id} (sfx): no sound {item.params.asset}")
        label = f"[sfx{item.id}]"
        parts.append(sound_filter(item, path, sound_seconds(path), label, rubberband))
        labels.append(label)
    duck = duck_filter(speech, sounds)
    bus = [f"amix=inputs={len(labels)}:duration=longest:normalize=0"]
    if len(labels) == 1:
        bus = [NO_SFX_FILTER]
    if duck:
        bus.append(duck)
    if silences:
        bus += ["asetpts=N/SR/TB", gate_filter(silences, MUTE_RAMP_S, inside=False)]
    parts.append(f"{''.join(labels)}{','.join(bus)}{SFX_BUS}")
    parts.append(f"{source}{SFX_BUS}amix=inputs=2:duration=first:normalize=0{out}")
    return ";".join(parts)
