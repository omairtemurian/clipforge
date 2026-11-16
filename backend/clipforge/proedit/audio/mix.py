"""The sound of a Pro Edit render (SPEC-v3 3.3, 3.6): the clip's sound
through the dialogue chain (DIALOGUE_FILTER), then the SFX (sfx_mix, muted
in the silences before drops), then the music beds (music_bed), then the
audio effects on all of it (fx), then the master filter (the final loudness:
pipeline/loudnorm's second pass at the project's target_lufs, -14 LUFS with
a true peak under -1 dBTP; its first pass measures the same graph)."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from clipforge.proedit.audio.envelope import Span
from clipforge.proedit.audio.fx import fx_graph, fx_items
from clipforge.proedit.audio.music_bed import music_beds, music_graph, silence_spans
from clipforge.proedit.audio.sfx_mix import NO_SFX_FILTER, audio_graph
from clipforge.proedit.audio.sounds import sfx_items
from clipforge.proedit.edl import TypedEdlItem

Stage = Callable[[str, str], str]

# The dialogue chain: rumble out below 80 Hz, a presence boost at 3 kHz, a
# gentle 3:1 compressor with make-up gain, then the de-esser.
DIALOGUE_FILTER = (
    "highpass=f=80,"
    "equalizer=f=3000:width_type=q:w=1:g=2.5,"
    "acompressor=threshold=0.1:ratio=3:attack=10:release=120:makeup=1.5,"
    "deesser=i=0.4:m=0.5:f=0.5"
)


def sound_graph(
    items: Sequence[TypedEdlItem],
    speech: Sequence[Span],
    library: Mapping[str, Path],
    source: str,
    out: str,
    *,
    dialogue: bool = False,
    master: str = "",
    loop: str = "",
) -> str:
    """Return the filters that play the sound items of items (SFX, music
    beds, silences before drops, audio effects; their sounds found in
    library or bundled) over the sound labelled source, ducked under the
    speech spans, into out; only the stages with items are in it (source
    passes through untouched when none is).

    With dialogue, source first goes through DIALOGUE_FILTER; with loop
    (render/loop_end.loop_sound) the mix then crossfades into its opening;
    with master (audio filters, e.g. the loudness pass), the whole mix ends
    in them.
    """
    silences = silence_spans(items)
    stages: list[Stage] = []
    if dialogue:
        stages.append(lambda into, to: f"{into}{DIALOGUE_FILTER}{to}")
    if sfx_items(items):
        stages.append(
            lambda into, to: audio_graph(
                items, speech, library, into, to, silences=silences
            )
        )
    if music_beds(items):
        stages.append(lambda into, to: music_graph(items, speech, library, into, to))
    if fx_items(items):
        stages.append(lambda into, to: fx_graph(items, into, to))
    if loop:
        stages.append(lambda into, to: f"{into}{loop}{to}")
    if master:
        stages.append(lambda into, to: f"{into}{master}{to}")
    if not stages:
        return f"{source}{NO_SFX_FILTER}{out}"
    labels = [source, *(f"[pro_sound{n}]" for n in range(1, len(stages))), out]
    return ";".join(
        stage(into, to)
        for stage, into, to in zip(stages, labels, labels[1:], strict=False)
    )
