"""Kinetic captions as ASS (SPEC-v3 3.3): per-word pop and bounce, shake on
loud words, scale on emphasis words, neon glow, single-word pages and emoji
pops, through the caption engine (pipeline/captions) with its own word
writer, so the existing templates draw as before.

Every moving tag belongs to the active word, the one being spoken (an event
shows its page while one word is active; tag times count from the event's
start, the word's start):

- pop: the word grows from POP_FROM percent past its size by POP_OVER
  percent points in POP_MS, then settles back in another POP_MS.
- bounce: from BOUNCE_FROM percent over its size by BOUNCE_OVER points in
  BOUNCE_MS, under it by BOUNCE_UNDER points in the next BOUNCE_MS, back to
  its size in a third.
- shake: a loud word (loud.loud_words) swings like an existing shake template's
  emphasis word does (caption_effects.shake_tags).
- glow: the word keeps primary_color and gets a halo of highlight_color:
  a stroke of GLOW_BORDER_RATIO of the font size, blurred by GLOW_BLUR_RATIO.
- emoji pop: the emoji after the active word grows from EMOJI_FROM percent to
  EMOJI_OVER and settles to 100 in EMOJI_MS each; other words show their
  emoji still, once spoken (an upcoming word's emoji is invisible).

Emphasis words of the clip are drawn at emphasis_scale percent whether or not
they are active (the existing engine's EMPHASIS_SCALE is 110).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from clipforge.captions_templates import CaptionTemplate
from clipforge.fonts import EMOJI_FONT
from clipforge.pipeline.caption_effects import (
    HIDDEN,
    WordWriter,
    bgr,
    escape,
    scale,
    shake_tags,
    word_color,
)
from clipforge.pipeline.caption_lines import CaptionWord, word_key
from clipforge.pipeline.captions import build_ass
from clipforge.proedit.captions.styles import Motion, get_style
from clipforge.proedit.edl_params import CaptionStyleParams

POP_FROM, POP_OVER, POP_MS = 70, 8, 90
BOUNCE_FROM, BOUNCE_OVER, BOUNCE_UNDER, BOUNCE_MS = 80, 15, 4, 80
GLOW_BORDER_RATIO, GLOW_BLUR_RATIO = 0.12, 0.06
EMOJI_FROM, EMOJI_OVER, EMOJI_MS = 30, 130, 90


@dataclass(frozen=True)
class KineticFx:
    """How kinetic captions move: the spoken word's motion, whether it
    glows, the percent size of emphasis words, whether loud words shake and
    the starts (ms) of the loud words (loud.loud_words)."""

    motion: Motion
    glow: bool
    emphasis_percent: int
    shake_on_loud: bool
    loud: frozenset[int] = frozenset()


def motion_tags(motion: Motion, size: int) -> str:
    """Return the tags that animate the active word's size (percent) as
    motion says, ending at size."""
    if motion == "pop":
        steps = [(POP_FROM, 0), (size + POP_OVER, POP_MS), (size, 2 * POP_MS)]
    else:
        steps = [
            (BOUNCE_FROM, 0),
            (size + BOUNCE_OVER, BOUNCE_MS),
            (size - BOUNCE_UNDER, 2 * BOUNCE_MS),
            (size, 3 * BOUNCE_MS),
        ]
    first = f"{scale(steps[0][0])}"
    moves = (
        f"\\t({before[1]},{after[1]},{scale(after[0])})"
        for before, after in zip(steps, steps[1:], strict=False)
    )
    return first + "".join(moves)


def glow_tags(template: CaptionTemplate) -> str:
    """Return the tags of the halo: a blurred stroke in highlight_color."""
    border = round(template.size * GLOW_BORDER_RATIO)
    blur = round(template.size * GLOW_BLUR_RATIO)
    return f"\\3c&H{bgr(template.highlight_color)}&\\bord{border}\\blur{blur}"


def emoji_pop_tags() -> str:
    """Return the tags that make an emoji pop in."""
    return (
        f"{scale(EMOJI_FROM)}\\t(0,{EMOJI_MS},{scale(EMOJI_OVER)})"
        f"\\t({EMOJI_MS},{2 * EMOJI_MS},{scale(100)})"
    )


def active_color(
    word: CaptionWord, template: CaptionTemplate, fx: KineticFx
) -> str | None:
    """Return the color of the active word: primary_color in a glow style
    (the halo is highlight_color), else what the engine says."""
    if fx.glow:
        return template.primary_color
    return word_color(word, True, template)


def kinetic_word_text(
    word: CaptionWord,
    active: bool,
    template: CaptionTemplate,
    emoji_map: Mapping[str, str],
    fx: KineticFx,
    *,
    upcoming: bool = False,
) -> str:
    """Return word as a kinetic caption line shows it.

    The active word gets the motion, glow and shake tags; an emphasis word
    that is not active only its size and color; the emoji of a mark or, if
    the template has emoji on, of the word's key follows it.
    """
    text = escape(word.text.upper() if template.uppercase else word.text)
    color = (
        active_color(word, template, fx)
        if active
        else word_color(word, False, template)
    )
    size = fx.emphasis_percent if word.emphasis else 100
    tags = f"\\c&H{bgr(color)}&" if color is not None else ""
    if active:
        tags += glow_tags(template) if fx.glow else ""
        if fx.shake_on_loud and word.start in fx.loud:
            tags += shake_tags()
        tags += motion_tags(fx.motion, size)
    elif word.emphasis:
        tags += scale(size)
    shown = f"{{{tags}}}{text}{{\\r}}" if tags else text
    emoji = word.emoji
    if emoji is None and template.emoji:
        emoji = emoji_map.get(word_key(word.text))
    if not emoji:
        return shown
    emoji_tags = f"\\fn{EMOJI_FONT}"
    if active:
        emoji_tags += emoji_pop_tags()
    elif upcoming:
        emoji_tags += HIDDEN
    return f"{shown} {{{emoji_tags}}}{emoji}{{\\r}}"


def word_writer(fx: KineticFx) -> WordWriter:
    """Return the caption engine's word writer that draws words with fx."""

    def write(
        word: CaptionWord,
        active: bool,
        template: CaptionTemplate,
        emoji_map: Mapping[str, str],
        *,
        upcoming: bool = False,
    ) -> str:
        return kinetic_word_text(
            word, active, template, emoji_map, fx, upcoming=upcoming
        )

    return write


def kinetic_ass(
    words: Sequence[CaptionWord],
    params: CaptionStyleParams,
    frame: tuple[int, int],
    *,
    emphasis_words: Sequence[str] = (),
    speaker_colors: Mapping[str, str] | None = None,
    loud: frozenset[int] = frozenset(),
    emoji_map: Mapping[str, str],
) -> str:
    """Return the ASS file of kinetic captions that show words (times in ms
    of the rendered clip) with the style params name on a frame of (width,
    height) pixels.

    emphasis_words and speaker_colors work as in pipeline/captions.build_ass;
    params.emoji turns the emoji of emoji_map on, loud holds the starts (ms)
    of the words that shake (loud.loud_words) if params.shake_on_loud.
    """
    style = get_style(params.style)
    template = style.caption.model_copy(update={"emoji": params.emoji})
    fx = KineticFx(
        style.motion,
        style.glow,
        round(params.emphasis_scale * 100),
        params.shake_on_loud,
        loud,
    )
    return build_ass(
        words,
        template,
        frame,
        emphasis_words=emphasis_words,
        speaker_colors=speaker_colors,
        emoji_map=emoji_map,
        word_writer=word_writer(fx),
    )
