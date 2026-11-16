"""Kinetic captions in a Pro Edit render (SPEC-v3 3.3, 3.6).

Each caption_style item shows the words of the base (base.ProEditBase.words,
in milliseconds of the rendered clip) that start in its window, cut off at
its end, in its style: caption_files writes one ASS file of kinetic captions
(captions/kinetic.kinetic_ass) per item with words, sized to the frame, with
the clip's emphasis words and speaker colors and the template emoji map.
The loud words that shake (params.shake_on_loud) are read from the base's
sound, cut and censored as the render plays it (captions/loud.loud_words on
its 16 kHz mono samples), only when an item asks for them. The caption stage
(graph.STAGES, after the overlays) draws each file with libass
(render_graph.subtitles_filter); an item without a file draws nothing.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np

from clipforge.captions_templates import load_emoji_map
from clipforge.ffmpeg import Arg, FFmpegError, run_ffmpeg
from clipforge.models import EdlKind
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.render import RenderError
from clipforge.pipeline.render_graph import AUDIO_OUT, audio_graph, subtitles_filter
from clipforge.pipeline.step import write_text
from clipforge.proedit.captions.kinetic import kinetic_ass
from clipforge.proedit.captions.loud import envelope_of, loud_words
from clipforge.proedit.edl import CaptionStyleItem, TypedEdlItem
from clipforge.proedit.render.base import ProEditBase
from clipforge.proedit.render.canvas import Canvas

CAPTION_KINDS: frozenset[EdlKind] = frozenset({"caption_style"})
LOUD_SAMPLE_RATE = 16_000
NO_AUDIO_FILTER = "anull"


def caption_items(items: Sequence[TypedEdlItem]) -> list[CaptionStyleItem]:
    """Return the caption_style items of items."""
    return [item for item in items if isinstance(item, CaptionStyleItem)]


def item_words(words: Sequence[CaptionWord], item: TypedEdlItem) -> list[CaptionWord]:
    """Return the words that start in item's window, cut off at its end."""
    start, end = round(item.t_start * 1000), round(item.t_end * 1000)
    return [
        replace(word, end=min(word.end, end))
        for word in words
        if start <= word.start < end
    ]


def caption_files(
    base: ProEditBase,
    items: Sequence[TypedEdlItem],
    frame: tuple[int, int],
    folder: Path,
    stem: str,
    loud: frozenset[int] = frozenset(),
) -> dict[int, Path]:
    """Write the ASS file of each caption_style item of items that shows
    words, for a frame of (width, height) pixels, into folder as
    <stem>.captions<item id>.ass, and return the files by item id; loud
    holds the starts (ms) of the words that shake."""
    files: dict[int, Path] = {}
    emoji_map = load_emoji_map()
    for item in caption_items(items):
        words = item_words(base.words, item)
        if not words:
            continue
        text = kinetic_ass(
            words,
            item.params,
            frame,
            emphasis_words=base.emphasis_words,
            speaker_colors=base.speaker_colors,
            loud=loud,
            emoji_map=emoji_map,
        )
        path = folder / f"{stem}.captions{item.id}.ass"
        write_text(path, text)
        files[item.id] = path
    return files


def needs_loud_words(items: Sequence[TypedEdlItem]) -> bool:
    """Return whether a caption_style item of items shakes its loud words."""
    return any(item.params.shake_on_loud for item in caption_items(items))


def loud_starts(base: ProEditBase, inputs: Sequence[Arg], fps: int) -> frozenset[int]:
    """Return the starts (ms) of the base's loud words (captions/loud), from
    its sound read with the ffmpeg inputs, cut and censored as the render
    plays it. Raises RenderError if ffmpeg cannot decode it."""
    graph = audio_graph(base.cuts(fps), base.censor or NO_AUDIO_FILTER)
    try:
        result = run_ffmpeg(
            [
                *inputs, "-filter_complex", graph, "-map", AUDIO_OUT,
                "-ac", "1", "-ar", str(LOUD_SAMPLE_RATE), "-f", "f32le", "pipe:1",
            ]
        )  # fmt: skip
    except FFmpegError as exc:
        raise RenderError(f"cannot read the sound of the clip: {exc}") from exc
    data = result.stdout[: len(result.stdout) // 4 * 4]
    samples = np.frombuffer(data, dtype="<f4").astype(np.float32)
    return loud_words(base.words, envelope_of(samples))


def caption_filters(items: Sequence[TypedEdlItem], canvas: Canvas) -> list[str]:
    """Return the subtitles filters that draw the caption files of items on
    canvas (canvas.captions, by item id)."""
    return [
        subtitles_filter(canvas.captions[item.id])
        for item in items
        if item.id in canvas.captions
    ]


def remove_files(files: Mapping[int, Path]) -> None:
    """Delete the caption files that a render wrote."""
    for path in files.values():
        path.unlink(missing_ok=True)
