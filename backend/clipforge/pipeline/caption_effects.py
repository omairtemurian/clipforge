"""How caption words look and move in ASS override tags (SPEC-v2 3.4).

A caption event (pipeline/captions) shows a page of caption lines while one
of its words is spoken, the active word. word_text draws one word: the
active word in highlight_color, other emphasis words in emphasis_color,
the other words of a speaker with a color in that color, emphasis words
EMPHASIS_SCALE percent tall, and the emoji that a mark gave the word (else
that of its keyword) after it. page_text joins the words of a page, and
the template's animation moves them (tag times count from the event's
start, the active word's start):

- pop: the active word grows from POP_FROM percent to its size in POP_MS.
- bounce: the active word grows from BOUNCE_FROM percent to BOUNCE_OVER
  percent points above its size in BOUNCE_MS, then settles back in another
  BOUNCE_MS (the owner allows the active word at most 105%).
- fade: a page fades in over FADE_MS when its first event starts.
- reveal: the words after the active word are invisible (\\alpha&HFF&), so
  words show once spoken; they still take their place, so lines do not
  move.
- shake: an emphasis word trembles (\\frz swings of SHAKE_DEGREES) over
  SHAKE_MS while it is the active word.
- underline: the active word is underlined (\\u1).
- pill: the active word keeps the template's primary_color and gets a
  rounded pill of highlight_color behind it: a stroke of PILL_SIZE_RATIO of
  the font size, which libass draws with round joins under every word's fill.
- hollow: the words other than the active one are outlines only (fill
  \\1a&HFF&, stroke in the word's color); the active word is filled with
  highlight_color.

ASS override colors are &HBBGGRR&; \\t animates \\fscx/\\fscy between two
times and \\fad fades a whole event in (Aegisub ASS tag reference, libass).

Right-to-left text (Persian, Arabic, Hebrew) is written in logical order;
libass shapes it with HarfBuzz and orders it with FriBidi. A style's
Encoding sets the base direction of its lines: -1 lets libass find it from
the text (FRIBIDI_PAR_ON, libass ass_shaper.c ass_resolve_base_direction),
any other value is left to right (encoding).
"""

import unicodedata
from collections.abc import Mapping, Sequence
from typing import Protocol

from clipforge.captions_templates import CaptionTemplate
from clipforge.fonts import EMOJI_FONT
from clipforge.pipeline.caption_lines import CaptionWord, word_key

# The size of emphasis words, in percent.
EMPHASIS_SCALE = 110
POP_FROM, POP_MS = 75, 120
BOUNCE_FROM, BOUNCE_OVER, BOUNCE_MS = 85, 5, 90
FADE_MS = 150
SHAKE_DEGREES, SHAKE_MS = 4, 60
PILL_SIZE_RATIO = 0.14
HIDDEN = "\\alpha&HFF&"
# ASS style Encoding: 1 the default (left-to-right lines), -1 base direction
# from the text.
LTR_ENCODING, AUTO_DIRECTION_ENCODING = 1, -1


def bgr(color: str) -> str:
    """Return a #RRGGBB color as the BBGGRR hex digits of ASS colors:
    "#ffd23f" -> "3FD2FF"."""
    return (color[5:7] + color[3:5] + color[1:3]).upper()


def encoding(text: str) -> int:
    """Return the ASS Encoding of a style that draws text: -1 (base direction
    from the text) if text has a right-to-left letter (Unicode bidi class R
    or AL), else 1, so a sentence's final punctuation goes to its left in
    right-to-left lines."""
    rtl = any(unicodedata.bidirectional(char) in ("R", "AL") for char in text)
    return AUTO_DIRECTION_ENCODING if rtl else LTR_ENCODING


def escape(text: str) -> str:
    """Return text as one line of Dialogue text that libass shows as written.

    Whitespace runs become one space. Braces become the escapes \\{ and \\},
    so they do not open or close override blocks, and a WORD JOINER follows
    each backslash, so it does not start an escape such as \\N.
    """
    text = " ".join(text.split()).replace("\\", "\\\u2060")
    return text.replace("{", "\\{").replace("}", "\\}")


def scale(percent: int) -> str:
    """Return the tags that make text percent tall and wide."""
    return f"\\fscx{percent}\\fscy{percent}"


def size_tags(word: CaptionWord, active: bool, template: CaptionTemplate) -> str:
    """Return the tags of word's size: EMPHASIS_SCALE for an emphasis word,
    animated from smaller for the active word of a pop or bounce template."""
    size = EMPHASIS_SCALE if word.emphasis else 100
    if active and template.animation == "pop":
        return f"{scale(POP_FROM)}\\t(0,{POP_MS},{scale(size)})"
    if active and template.animation == "bounce":
        over, settled = BOUNCE_MS, 2 * BOUNCE_MS
        return (
            f"{scale(BOUNCE_FROM)}\\t(0,{over},{scale(size + BOUNCE_OVER)})"
            f"\\t({over},{settled},{scale(size)})"
        )
    return scale(size) if word.emphasis else ""


def shake_tags() -> str:
    """Return the tags that swing a word to both sides and back."""
    swings = (SHAKE_DEGREES, -SHAKE_DEGREES, SHAKE_DEGREES // 2, 0)
    return "\\frz0" + "".join(
        f"\\t({i * SHAKE_MS},{(i + 1) * SHAKE_MS},\\frz{angle})"
        for i, angle in enumerate(swings)
    )


def word_color(
    word: CaptionWord, active: bool, template: CaptionTemplate
) -> str | None:
    """Return the color of word, or None for the template's primary color:
    highlight_color if active (primary_color on its pill in a pill template),
    else the color a mark painted it, else emphasis_color for an emphasis
    word, else the word's speaker color."""
    if active:
        if template.animation == "pill":
            return template.primary_color
        return template.highlight_color
    if word.paint is not None:
        return word.paint
    return template.emphasis_color if word.emphasis else word.color


def style_tags(word: CaptionWord, active: bool, template: CaptionTemplate) -> str:
    """Return the tags of the effects that mark the active word (underline,
    pill) or move an emphasis word (shake)."""
    if not active:
        return ""
    if template.animation == "underline":
        return "\\u1"
    if template.animation == "pill":
        pill = round(template.size * PILL_SIZE_RATIO)
        return f"\\3c&H{bgr(template.highlight_color)}&\\bord{pill}"
    if template.animation == "shake" and word.emphasis:
        return shake_tags()
    return ""


def word_text(
    word: CaptionWord,
    active: bool,
    template: CaptionTemplate,
    emoji_map: Mapping[str, str],
    *,
    upcoming: bool = False,
) -> str:
    """Return word as a caption line shows it, with template's case.

    The active word is in highlight_color, another emphasis word in
    emphasis_color, any other in the color of its speaker (word.color) if
    it has one; sizes come from size_tags. An upcoming word (after the
    active one) is invisible in a reveal template. The emoji that a mark
    gave the word (word.emoji; "" none) follows it in EMOJI_FONT, whatever
    the template says; without a mark, the emoji of the word's key in
    emoji_map follows it if the template has emoji on.
    """
    text = escape(word.text.upper() if template.uppercase else word.text)
    tags = ""
    color = word_color(word, active, template)
    if template.animation == "hollow" and not active:
        stroke = color or template.primary_color
        tags = f"\\1a&HFF&\\3c&H{bgr(stroke)}&"
    elif color is not None:
        tags = f"\\c&H{bgr(color)}&"
    tags += style_tags(word, active, template)
    tags += size_tags(word, active, template)
    hidden = upcoming and template.animation == "reveal"
    if hidden:
        tags += HIDDEN
    shown = f"{{{tags}}}{text}{{\\r}}" if tags else text
    emoji = word.emoji
    if emoji is None and template.emoji:
        emoji = emoji_map.get(word_key(word.text))
    if not emoji:
        return shown
    emoji_tags = f"\\fn{EMOJI_FONT}" + (HIDDEN if hidden else "")
    reset = "\\r" if hidden else "\\fn"
    return f"{shown} {{{emoji_tags}}}{emoji}{{{reset}}}"


class WordWriter(Protocol):
    """Draws one word of a page like word_text does (Pro Edit's kinetic
    captions draw their own)."""

    def __call__(
        self,
        word: CaptionWord,
        active: bool,
        template: CaptionTemplate,
        emoji_map: Mapping[str, str],
        *,
        upcoming: bool = False,
    ) -> str: ...


def page_text(
    page: Sequence[Sequence[CaptionWord]],
    active: int,
    template: CaptionTemplate,
    emoji_map: Mapping[str, str],
    *,
    first: bool,
    word_writer: WordWriter = word_text,
) -> str:
    """Return the Dialogue text of page while its word number active
    (counting from 0 across its lines) is spoken: its lines joined by \\N,
    words joined by spaces, each drawn by word_writer. The page's first
    event fades in if the template's animation is fade."""
    position = 0
    lines = []
    for line in page:
        texts = []
        for word in line:
            texts.append(
                word_writer(
                    word,
                    position == active,
                    template,
                    emoji_map,
                    upcoming=position > active,
                )
            )
            position += 1
        lines.append(" ".join(texts))
    fading = first and template.animation == "fade"
    fade = f"{{\\fad({FADE_MS},0)}}" if fading else ""
    return fade + "\\N".join(lines)
