"""The music of a Pro Edit render (SPEC-v3 3.3, 3.6): music beds ducked under
speech, with silences before drops.

Each music_bed item's sound (sounds.find_sound: a library asset id or a
bundled loop) is read by an `amovie` source looped forever (`loop=0`;
`asetpts=N/SR/TB` makes the loops' timestamps run on, else `atrim` never
sees the end), brought to SAMPLE_RATE, cut from its music offset
(bed_offsets) for the item's length, faded over BED_FADE_S at both ends
(no click where the music stops for a silence and comes back on the drop),
set to params.gain_db and delayed (`adelay`, then `asetpts=N/SR/TB`: its
padding frames have no timestamp for the ducking's t) to the item's
start. A bed
with params.duck is lowered by params.duck_db under the base's speech spans
that it plays over (sfx_mix.duck_filter: the same span ducking as the SFX).

The "sidechain" of the ducking is the transcript's speech spans, not the
clip's level as in the v2 music (pipeline/music.duck_filter,
sidechaincompress), whose dip depends on how loud the speech is: a plan's
duck_db is then the dip, exactly (docs/decisions.md).

A silence_before_drop shares the music track with the beds, so no bed
plays in it: the music around it is two beds, the second one continuing
the music (bed_offsets), and the drop is where the second one starts. The
silence also mutes the SFX (sfx_mix.audio_graph's silences), so a riser is
cut by it; the speech is never muted. The beds are added up (`amix`,
normalize=0) and added to the program's sound, which keeps its length.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

from clipforge.ffmpeg import filter_value
from clipforge.proedit.audio.envelope import Span
from clipforge.proedit.audio.sfx_mix import NO_SFX_FILTER, SAMPLE_RATE, duck_filter
from clipforge.proedit.audio.sounds import find_sound
from clipforge.proedit.edl import MusicBedItem, SilenceBeforeDropItem, TypedEdlItem

BED_FADE_S = 0.01
MUSIC_BUS = "[music_bus]"


def music_beds(items: Sequence[TypedEdlItem]) -> list[MusicBedItem]:
    """Return the music beds of items in time order."""
    beds = [item for item in items if isinstance(item, MusicBedItem)]
    return sorted(beds, key=lambda bed: (bed.t_start, bed.id))


def silence_spans(items: Sequence[TypedEdlItem]) -> list[Span]:
    """Return the (start, end) seconds of the silences before drops of
    items, in time order."""
    return sorted(
        (item.t_start, item.t_end)
        for item in items
        if isinstance(item, SilenceBeforeDropItem)
    )


def bed_offsets(beds: Sequence[MusicBedItem]) -> dict[int, float]:
    """Return the music second each bed (in time order) starts at, by id:
    its params.offset, else where the music of the bed of the same asset
    before it would be at its start (0 for the first bed of an asset)."""
    offsets: dict[int, float] = {}
    last: dict[str, MusicBedItem] = {}
    for bed in beds:
        before = last.get(bed.params.asset)
        if bed.params.offset is not None:
            offsets[bed.id] = bed.params.offset
        elif before is None:
            offsets[bed.id] = 0.0
        else:
            offsets[bed.id] = offsets[before.id] + bed.t_start - before.t_start
        last[bed.params.asset] = bed
    return offsets


def bed_filter(
    bed: MusicBedItem,
    path: Path,
    offset: float,
    speech: Sequence[Span],
    label: str,
) -> str:
    """Return the chain that plays bed's sound path from offset seconds
    into the music, as the module docstring says, into label."""
    length = bed.t_end - bed.t_start
    fade = min(BED_FADE_S, length / 2)
    filters = [
        f"amovie=filename={filter_value(str(path.absolute()))}:loop=0",
        f"aresample={SAMPLE_RATE}",
        "asetpts=N/SR/TB",
        f"atrim=start={offset:.6f}:duration={length:.6f}",
        "asetpts=PTS-STARTPTS",
        f"afade=t=in:st=0:d={fade:.6f}",
        f"afade=t=out:st={length - fade:.6f}:d={fade:.6f}",
        f"volume={bed.params.gain_db:g}dB",
        f"adelay=delays={bed.t_start * 1000:.3f}:all=1",
        "asetpts=N/SR/TB",
    ]
    if bed.params.duck and bed.params.duck_db > 0:
        duck = duck_filter(speech, [bed], bed.params.duck_db)
        filters += [duck] if duck else []
    return ",".join(filters) + label


def music_graph(
    items: Sequence[TypedEdlItem],
    speech: Sequence[Span],
    library: Mapping[str, Path],
    source: str,
    out: str,
) -> str:
    """Return the filters that mix the music beds of items (their sounds
    found by sounds.find_sound in library: all must be, graph.undrawn) into
    the sound labelled source, into out; source passes through untouched
    when there are none."""
    beds = music_beds(items)
    if not beds:
        return f"{source}{NO_SFX_FILTER}{out}"
    offsets = bed_offsets(beds)
    parts, labels = [], []
    for bed in beds:
        path = find_sound(bed.params.asset, library)
        if path is None:
            raise ValueError(f"item {bed.id} (music_bed): no sound {bed.params.asset}")
        label = f"[bed{bed.id}]"
        parts.append(bed_filter(bed, path, offsets[bed.id], speech, label))
        labels.append(label)
    bus = f"amix=inputs={len(labels)}:duration=longest:normalize=0"
    if len(labels) == 1:
        bus = NO_SFX_FILTER
    parts.append(f"{''.join(labels)}{bus}{MUSIC_BUS}")
    parts.append(f"{source}{MUSIC_BUS}amix=inputs=2:duration=first:normalize=0{out}")
    return ";".join(parts)
