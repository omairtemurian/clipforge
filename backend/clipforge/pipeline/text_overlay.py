"""Text overlays of a clip's timeline (SPEC-v2 3.5): the items of its text
track, at most MAX_TEXT_LAYERS of them, each drawn by one ffmpeg drawtext
filter from its TextProps (font, size, colors, stroke, box, position) only
between its start and end, with its in and out animations.

drawtext evaluates alpha, x, y and fontsize again on every frame (t is the
frame's time in the rendered clip), so an animation is an expression of t:
its progress eases out (1 - (1 - p)^2) from 0 at the item's start to 1
after in_seconds, and back from 1 to 0 over the last out_seconds. A text
with line breaks is drawn as lines centred on each other.
"""

import textwrap
from collections.abc import Sequence
from pathlib import Path

from clipforge.ffmpeg import filter_value
from clipforge.models import TextAnimation, TextProps, TrackItem

# The most text items a clip's text track holds.
MAX_TEXT_LAYERS = 5
# The padding of a text box, in font sizes.
BOX_PADDING = 0.25
# How far a slide moves the text, in fractions of the frame's size.
SLIDE_DISTANCE = 0.15
# The space between the lines of a text, in font sizes.
LINE_SPACING = 0.1
# The font size a pop starts from (in) or ends at (out), times the size.
POP_FROM = 0.6
# The (x, y) direction each slide moves the text in.
SLIDES: dict[TextAnimation, tuple[int, int]] = {
    "slide_up": (0, -1),
    "slide_down": (0, 1),
    "slide_left": (-1, 0),
    "slide_right": (1, 0),
}


def text_layer_problems(items: Sequence[TrackItem]) -> list[str]:
    """Return what is wrong with the items of a text track as a whole: more
    than MAX_TEXT_LAYERS of them; an empty list if nothing is."""
    if len(items) <= MAX_TEXT_LAYERS:
        return []
    return [
        f"text track: {len(items)} text overlays, at most {MAX_TEXT_LAYERS} allowed"
    ]


def animation_seconds(props: TextProps, length: float) -> tuple[float, float]:
    """Return how many seconds the in and the out animation of props last
    in an item length seconds long: 0 for "none", else in_seconds and
    out_seconds, both shortened in proportion when together they are
    longer than the item."""
    seconds_in = props.in_seconds if props.animation_in != "none" else 0.0
    seconds_out = props.out_seconds if props.animation_out != "none" else 0.0
    total = seconds_in + seconds_out
    if total > length > 0:
        scale = length / total
        seconds_in, seconds_out = seconds_in * scale, seconds_out * scale
    return seconds_in, seconds_out


def text_filter(
    props: TextProps, font: Path, height: int, start: float, end: float
) -> str:
    """Return the drawtext filter that draws props' text with the font file
    font on frames height pixels tall, animated for an item from start to
    end seconds of the rendered clip (no %{...} expansion, so the text is
    drawn as written). The caller adds the enable window."""
    size = max(round(props.size * height), 1)
    seconds_in, seconds_out = animation_seconds(props, end - start)
    shown_in = eased(f"(t-{start:.3f})/{seconds_in:.3f}") if seconds_in else ""
    shown_out = eased(f"({end:.3f}-t)/{seconds_out:.3f}") if seconds_out else ""
    x, y = f"w*{props.x:g}-text_w/2", f"h*{props.y:g}-text_h/2"
    for animation, shown, sign in (
        (props.animation_in, shown_in, -1),
        (props.animation_out, shown_out, 1),
    ):
        dx, dy = SLIDES.get(animation, (0, 0))
        if shown and dx:
            x += f"{'+' if dx * sign > 0 else '-'}w*{SLIDE_DISTANCE:g}*(1-{shown})"
        if shown and dy:
            y += f"{'+' if dy * sign > 0 else '-'}h*{SLIDE_DISTANCE:g}*(1-{shown})"
    parts = [
        f"drawtext=fontfile={filter_value(str(font.absolute()))}",
        f"text={_text_value(props.text)}",
        "expansion=none",
        f"fontsize={_font_size(props, size, shown_in, shown_out)}",
        f"fontcolor=0x{props.color[1:]}",
    ]
    if props.stroke is not None:
        width = max(round(size * props.stroke_width), 1)
        parts += [f"borderw={width}", f"bordercolor=0x{props.stroke[1:]}"]
    if "\n" in props.text:
        spacing = round(size * LINE_SPACING)
        parts += ["text_align=C", f"line_spacing={spacing}"]
    parts += [_option("x", x), _option("y", y)]
    alpha = "*".join(shown for shown in (shown_in, shown_out) if shown)
    if alpha:
        parts.append(f"alpha='{alpha}'")
    if props.box is not None:
        padding = max(round(size * BOX_PADDING), 1)
        opacity = "" if props.box_opacity == 1 else f"@{props.box_opacity:g}"
        parts += [
            "box=1",
            f"boxcolor=0x{props.box[1:]}{opacity}",
            f"boxborderw={padding}",
        ]
    return ":".join(parts)


def wrap_lines(text: str, width: int, max_lines: int) -> list[str]:
    """Return the words of text wrapped to lines of at most width
    characters, or wider lines if more than max_lines would be needed (a
    longer word is a line of its own); no lines for blank text."""
    lines = textwrap.wrap(text, width, break_long_words=False)
    while len(lines) > max_lines:
        width += 1
        lines = textwrap.wrap(text, width, break_long_words=False)
    return lines


def fit_scale(lines: Sequence[str], width: int) -> float:
    """Return the scale of a font size that fits the longest of lines in
    width characters (1 if it fits already)."""
    longest = max((len(line) for line in lines), default=1)
    return min(1.0, width / longest)


def eased(progress: str) -> str:
    """Return the expression of progress (an expression of t) clipped to
    [0, 1] and eased out."""
    return f"(1-pow(1-clip({progress},0,1),2))"


def _font_size(props: TextProps, size: int, shown_in: str, shown_out: str) -> str:
    """Return the drawtext fontsize: size, growing from POP_FROM times it
    for a pop in and shrinking back to that for a pop out."""
    scales = [
        f"({POP_FROM:g}+{1 - POP_FROM:g}*{shown})"
        for animation, shown in (
            (props.animation_in, shown_in),
            (props.animation_out, shown_out),
        )
        if animation == "pop" and shown
    ]
    if not scales:
        return str(size)
    return f"'{size}*{'*'.join(scales)}'"


def _text_value(text: str) -> str:
    """Return text as drawtext's text value: each line escaped
    (filter_value), joined by raw newlines, which drawtext breaks lines at
    (an escaped one is drawn as a backslash)."""
    return "\n".join(filter_value(line) for line in text.split("\n"))


def _option(name: str, expression: str) -> str:
    """Return the drawtext option name=expression, quoted when the
    expression has commas (which would end the filter in a graph)."""
    return f"{name}='{expression}'" if "," in expression else f"{name}={expression}"
