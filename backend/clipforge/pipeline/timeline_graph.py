"""The layers of a clip's timeline in its render (SPEC-v2 3.5).

A Layer is an item of a track other than the video track, as the render
draws or mixes it. The asset of each layer is one more ffmpeg input
(layer_inputs, numbered from 1 after the source); visual_graph puts the
B-roll, overlay and text layers (pipeline/text_overlay) on the clip's
frames after its cuts, in order (later layers on top), and mix_graph mixes
the music, sound effect and voiceover layers into the clip's sound (music
looped, faded and ducked under the clip's speech: pipeline/music; the
clip's own sound ducked under voiceover: pipeline/voiceover). Item
times are seconds of the rendered clip, so every layer shows only between
its start and end.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from clipforge.ffmpeg import Arg
from clipforge.models import (
    AudioProps,
    BrollProps,
    MusicProps,
    OverlayProps,
    TextProps,
    TrackItem,
    TrackName,
    VoiceoverProps,
)
from clipforge.pipeline.music import LOOP_ARGS, duck_filter, music_filters
from clipforge.pipeline.text_overlay import text_filter
from clipforge.pipeline.voiceover import duck_filter as voiceover_duck_filter
from clipforge.pipeline.voiceover import duck_windows

VISUAL_TRACKS: tuple[TrackName, ...] = ("broll", "overlays", "text")
AUDIO_TRACKS: tuple[TrackName, ...] = ("music", "sfx", "voiceover")
# The first ffmpeg input of the layers' assets: input 0 is the source.
FIRST_INPUT = 1

LayerProps = (
    BrollProps | OverlayProps | TextProps | AudioProps | MusicProps | VoiceoverProps
)


@dataclass(frozen=True)
class Layer:
    """The item of track, ending by the clip's end, with its props parsed
    and path, the file it plays (its asset's) or draws with (a text item's
    font)."""

    track: TrackName
    item: TrackItem
    props: LayerProps
    path: Path


def numbered(layers: Sequence[Layer]) -> list[tuple[Layer, int | None]]:
    """Return each layer with the number of its ffmpeg input: FIRST_INPUT,
    FIRST_INPUT + 1, ... for the layers that read a file, None for text."""
    inputs: list[tuple[Layer, int | None]] = []
    number = FIRST_INPUT
    for layer in layers:
        if layer.track == "text":
            inputs.append((layer, None))
        else:
            inputs.append((layer, number))
            number += 1
    return inputs


def layer_inputs(layers: Sequence[Layer], fps: int) -> list[Arg]:
    """Return the ffmpeg input options of the layers that read a file, in
    order: an image loops at fps frames a second for its item's length; a
    video or sound is read from its props' offset for that length, a music
    item's file looping (from its start) if it is shorter."""
    args: list[Arg] = []
    for layer, number in numbered(layers):
        if number is None:
            continue
        length = f"{layer.item.end - layer.item.start:.3f}"
        if layer.item.kind == "image":
            args += ["-loop", "1", "-framerate", str(fps), "-t", length]
        else:
            offset = getattr(layer.props, "offset", 0.0)
            if layer.track == "music":
                args += LOOP_ARGS
            args += ["-ss", f"{offset:.3f}", "-t", length]
        args += ["-i", layer.path]
    return args


def has_visuals(layers: Sequence[Layer]) -> bool:
    """Return whether any layer is drawn on the frames."""
    return any(layer.track in VISUAL_TRACKS for layer in layers)


def has_sounds(layers: Sequence[Layer]) -> bool:
    """Return whether any layer is mixed into the sound."""
    return any(layer.track in AUDIO_TRACKS for layer in layers)


def visual_graph(
    layers: Sequence[Layer], size: tuple[int, int], source: str, out: str
) -> str:
    """Return the filters that draw the B-roll, overlay and text layers, in
    order, on the size (width, height) frames labelled source, into out; ""
    if there are none.

    An asset's frames start at its item's start (setpts) and the overlay
    filter shows them until its end (enable), then passes the frames
    through once the asset ends (eof_action=pass).
    """
    visual = [pair for pair in numbered(layers) if pair[0].track in VISUAL_TRACKS]
    parts: list[str] = []
    current = source
    for index, (layer, number) in enumerate(visual):
        target = out if index == len(visual) - 1 else f"[layer{index}]"
        item = layer.item
        window = f"enable='between(t,{item.start:.3f},{item.end:.3f})'"
        if isinstance(layer.props, TextProps):
            text = text_filter(layer.props, layer.path, size[1], item.start, item.end)
            parts.append(f"{current}{text}:{window}{target}")
        else:
            asset = f"[asset{index}]"
            prepare, position = _placement(layer.props, size)
            shift = f"setpts=PTS-STARTPTS+{item.start:.6f}/TB"
            parts.append(f"[{number}:v:0]{prepare},{shift}{asset}")
            parts.append(
                f"{current}{asset}overlay={position}:eof_action=pass:{window}{target}"
            )
        current = target
    return ";".join(parts)


def mix_graph(layers: Sequence[Layer], source: str, out: str) -> str:
    """Return the filters that mix the music, sound effect and voiceover
    layers into the sound labelled source, into out; "" if there are none.

    Each sound is set to its volume (a music item also faded:
    music.music_filters) and delayed to its item's start; a music item that
    ducks is then compressed with source as its key (music.duck_filter;
    asplit gives each one its copy). While a voiceover item that ducks
    plays, source itself is lowered (voiceover.duck_filter; the music keys
    on it before that). amix adds them up without scaling them down
    (normalize=0) and lasts as long as source.
    """
    sounds = [pair for pair in numbered(layers) if pair[0].track in AUDIO_TRACKS]
    if not sounds:
        return ""
    ducking = [index for index, (layer, _) in enumerate(sounds) if _ducks(layer)]
    parts, labels = [], []
    if ducking:
        keys = "".join(f"[key{index}]" for index in ducking)
        parts.append(f"{source}asplit={len(ducking) + 1}[voice]{keys}")
        source = "[voice]"
    voiceovers = [
        (layer.item, layer.props)
        for layer, _ in sounds
        if isinstance(layer.props, VoiceoverProps)
    ]
    lowered = voiceover_duck_filter(duck_windows(voiceovers))
    if lowered:
        parts.append(f"{source}{lowered}[ducked]")
        source = "[ducked]"
    for index, (layer, number) in enumerate(sounds):
        delay = f"adelay=delays={round(layer.item.start * 1000)}:all=1"
        label = f"[mix{index}]"
        if index in ducking:
            parts.append(f"[{number}:a:0]{_sound_filters(layer)},{delay}[duck{index}]")
            parts.append(f"[duck{index}][key{index}]{duck_filter()}{label}")
        else:
            parts.append(f"[{number}:a:0]{_sound_filters(layer)},{delay}{label}")
        labels.append(label)
    parts.append(
        f"{source}{''.join(labels)}amix=inputs={len(labels) + 1}"
        f":duration=first:normalize=0{out}"
    )
    return ";".join(parts)


def _ducks(layer: Layer) -> bool:
    """Return whether layer is music that ducks under the clip's sound."""
    return isinstance(layer.props, MusicProps) and layer.props.duck


def _sound_filters(layer: Layer) -> str:
    """Return the filters that set a sound layer's volume (and fade music)."""
    props = layer.props
    if isinstance(props, MusicProps):
        return music_filters(props, layer.item.end - layer.item.start)
    volume = props.volume if isinstance(props, AudioProps) else 1.0
    return f"volume=volume={volume:g}"


def _placement(props: LayerProps, size: tuple[int, int]) -> tuple[str, str]:
    """Return the filters that prepare an asset's frames for size (width,
    height) frames and the overlay's x and y: a cutaway B-roll scaled to
    cover the frame and cut to it at (0, 0); an overlay or a
    picture-in-picture B-roll props.width of the frame wide, centered at
    (props.x, props.y), an overlay at its opacity."""
    width, height = size
    if isinstance(props, OverlayProps) or (
        isinstance(props, BrollProps) and props.mode == "pip"
    ):
        scaled = max(_even(round(width * props.width)), 2)
        prepare = f"scale={scaled}:-2,setsar=1"
        if isinstance(props, OverlayProps):
            prepare += f",format=yuva420p,colorchannelmixer=aa={props.opacity:g}"
        position = f"x=main_w*{props.x:g}-overlay_w/2:y=main_h*{props.y:g}-overlay_h/2"
        return prepare, position
    cover = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )
    return cover, "x=0:y=0"


def _even(value: int) -> int:
    """Round a non-negative value down to an even number."""
    return value - value % 2
