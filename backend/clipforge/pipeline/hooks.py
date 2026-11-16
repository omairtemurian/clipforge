"""The viral hook of a clip (SPEC-v2 3.5): over the first 2-3 s of its
render, its hook template (clipforge.hooks_templates) draws the hook's
text with animations, punches in on the frames and plays a whoosh.

hook_layers turns a clip's hook into layers that the render draws and
mixes like the timeline's (pipeline/timeline_graph): a text layer for each
of the template's layers, drawn on top of the text track's, and the
template's whoosh as a sound effect. clip_punch gives its punch-in, which
punch_filter draws on the frames after the cuts (t is the time in the
rendered clip), under the layers and captions. Hook times are seconds of
the rendered clip, so a hook always covers the clip's start, whatever its
sections and cuts.

caption_hook_text fills a hook from the opening words of the clip's
captions; hook_theme.theme_hook_text asks the LLM for a line instead.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from clipforge.hooks_templates import (
    TEXT_SLOT,
    HookTemplate,
    get_template,
    sound_path,
)
from clipforge.models import HOOK_TEXT_MAX, AudioProps, ClipHook, TrackItem
from clipforge.pipeline.layout_parts import zoomed_side
from clipforge.pipeline.text_overlay import eased, fit_scale, wrap_lines
from clipforge.pipeline.timeline_graph import Layer

logger = logging.getLogger(__name__)

# The ids of a hook's layer items: HOOK_ITEM-text-<n> and HOOK_ITEM-sound.
HOOK_ITEM = "hook"
# The most words that caption_hook_text takes from the captions.
CAPTION_WORDS_MAX = 8
# What ends a sentence, and what is left off the end of a hook's text.
SENTENCE_END = (".", "!", "?", "…")
TRAILING = ",;:.-–— "


@dataclass(frozen=True)
class Punch:
    """A hook's punch-in zoom in the rendered clip: the frames grow to
    scale times their size over attack seconds from its start and shrink
    back over release seconds up to end."""

    scale: float
    attack: float
    release: float
    end: float


def hook_template(hook: ClipHook) -> HookTemplate | None:
    """Return the template of hook; None (logged) if it no longer exists."""
    try:
        return get_template(hook.template)
    except ValueError as exc:
        logger.warning("hook left out: %s", exc)
        return None


def wrap_text(text: str, template: HookTemplate) -> tuple[str, float]:
    """Return text as template shows it, uppercased if it says so and
    wrapped to lines of at most its max_chars_per_line characters (wider
    lines if more than its max_lines would be needed), and the scale of
    its font size that fits the longest line in max_chars_per_line."""
    text = " ".join(text.upper().split() if template.uppercase else text.split())
    lines = wrap_lines(text, template.max_chars_per_line, template.max_lines)
    return "\n".join(lines), fit_scale(lines, template.max_chars_per_line)


def hook_layers(
    hook: ClipHook | None, length: float, fonts: Mapping[str, Path]
) -> list[Layer]:
    """Return the layers of hook in a clip whose render lasts length
    seconds: the text layers of its template, then its whoosh, all from 0
    to the hook's duration (cut to length). None, an unknown template and a
    layer whose font is gone (logged) give no layers."""
    template = hook_template(hook) if hook is not None else None
    if hook is None or template is None:
        return []
    end = min(hook.duration, length)
    text, scale = wrap_text(hook.text, template)
    layers = []
    for index, layer in enumerate(template.layers):
        if layer.font not in fonts:
            logger.warning("hook layer %d left out: no font %r", index, layer.font)
            continue
        props = layer.model_copy(
            update={
                "text": layer.text.replace(TEXT_SLOT, text),
                "size": layer.size * scale,
            }
        )
        item = TrackItem(id=f"{HOOK_ITEM}-text-{index}", kind="text", start=0, end=end)
        layers.append(Layer("text", item, props, fonts[layer.font]))
    sound = sound_path(template)
    if sound is not None:
        item = TrackItem(id=f"{HOOK_ITEM}-sound", kind="audio", start=0, end=end)
        props_audio = AudioProps(volume=template.sound_volume)
        layers.append(Layer("sfx", item, props_audio, sound))
    return layers


def clip_punch(hook: ClipHook | None, length: float) -> Punch | None:
    """Return the punch-in of hook in a clip whose render lasts length
    seconds; None if there is no hook, its template is unknown or has no
    punch. Its attack and release are shortened in proportion when
    together they are longer than the hook."""
    template = hook_template(hook) if hook is not None else None
    if hook is None or template is None or template.punch is None:
        return None
    end = min(hook.duration, length)
    punch = template.punch
    attack, release = punch.attack, punch.release
    if attack + release > end:
        shrink = end / (attack + release)
        attack, release = attack * shrink, release * shrink
    return Punch(punch.scale, attack, release, end)


def punch_filter(punch: Punch | None, size: tuple[int, int]) -> str:
    """Return the filters that punch size (width, height) frames in as punch
    says, about their centre: each frame is scaled up (scale with
    eval=frame, to even sizes) and cropped back to size; "" for None."""
    if punch is None:
        return ""
    width, height = size
    grow = eased(f"t/{punch.attack:.3f}")
    shrink = eased(f"({punch.end:.3f}-t)/{punch.release:.3f}")
    scale = f"1+{punch.scale - 1:.4f}*min({grow},{shrink})"
    scaled_w, scaled_h = zoomed_side(width, scale), zoomed_side(height, scale)
    return (
        f"scale=w='{scaled_w}':h='{scaled_h}':eval=frame,"
        f"crop=w={width}:h={height}"
        f":x='trunc(({scaled_w}-{width})/2)':y='trunc(({scaled_h}-{height})/2)',"
        "setsar=1"
    )


def caption_hook_text(words: Sequence[str]) -> str:
    """Return a hook's text from the opening words of a clip's captions: up
    to the end of the first sentence, at most CAPTION_WORDS_MAX words and
    HOOK_TEXT_MAX characters, without trailing commas, dashes or full
    stops; "" if there are no words."""
    taken: list[str] = []
    for word in (w.strip() for w in words):
        if not word:
            continue
        if len(" ".join([*taken, word])) > HOOK_TEXT_MAX:
            break
        taken.append(word)
        if len(taken) == CAPTION_WORDS_MAX or word.endswith(SENTENCE_END):
            break
    return " ".join(taken).rstrip(TRAILING)
