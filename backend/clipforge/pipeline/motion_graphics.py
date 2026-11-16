"""Motion graphics of a clip (SPEC-v2 3.5): the names, numbers, dates and
key phrases that the LLM picks from what is said (MotionGraphicPick,
clip_graphics.pick_motion_graphics) become animated text items on the
clip's text track at the moment they are said, in the project's brand
style (clipforge.brand_style).

Each pick quotes the words it goes with; quote_span finds them among the
clip's rendered words (times in the rendered clip, after its cuts), so a
graphic starts exactly on the first quoted word and shows for
MIN_SECONDS to MAX_SECONDS. Two original templates draw them:

- lower-third (names, key phrases): white text, and the label under it, on
  a box of the brand color in the lower part of the frame (above the
  captions), sliding in from the left and fading out;
- number callout (numbers, dates): big text in the brand color with a dark
  outline in the upper third, popping in and fading out.

Graphics of one template never overlap; their items have ids
MOTION_ITEM-<n> and replace the clip's earlier ones, and they are ordinary
text items afterwards, which the editor changes like any text overlay.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from clipforge.brand_style import BrandStyle
from clipforge.models import MotionGraphicKind, MotionGraphicPick, TextProps, TrackItem
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.text_overlay import MAX_TEXT_LAYERS, fit_scale, wrap_lines

logger = logging.getLogger(__name__)

GraphicTemplate = Literal["lower_third", "callout"]
# The template that draws each kind of motion graphic.
TEMPLATES: dict[MotionGraphicKind, GraphicTemplate] = {
    "name": "lower_third",
    "phrase": "lower_third",
    "number": "callout",
    "date": "callout",
}
# The id prefix of motion graphic items: MOTION_ITEM-<n>.
MOTION_ITEM = "mg"
# How long a graphic shows: from its first word to at least MIN_SECONDS
# after it (the end of its quote if later), at most MAX_SECONDS; one that
# the clip's end would cut below SHORTEST_SECONDS is left out.
MIN_SECONDS, MAX_SECONDS, SHORTEST_SECONDS = 2.0, 3.5, 0.75
# The least time between two graphics of one template.
GAP_SECONDS = 0.2
# Font size (times the frame's height), characters of a line at that size
# (in a 9:16 frame's width) and centre height of each template.
LOWER_THIRD_SIZE, LOWER_THIRD_CHARS, LOWER_THIRD_Y = 0.034, 22, 0.55
CALLOUT_SIZE, CALLOUT_CHARS, CALLOUT_Y = 0.075, 11, 0.33
# The text color of a lower-third, and the outline of a callout.
LOWER_THIRD_COLOR, CALLOUT_STROKE = "#FFFFFF", "#111111"


@dataclass(frozen=True)
class PlacedGraphic:
    """A pick placed in the rendered clip, from start to end seconds."""

    pick: MotionGraphicPick
    start: float
    end: float


def token(text: str) -> str:
    """Return text as quotes are matched: its letters and digits, case
    folded (punctuation and apostrophes left out)."""
    return "".join(char for char in text.casefold() if char.isalnum())


def quote_span(words: Sequence[CaptionWord], quote: str) -> tuple[int, int] | None:
    """Return the indexes of the first and last of words that say quote
    (its first occurrence, matched by token; words without letters or
    digits are skipped on both sides); None if they never say it."""
    wanted = [t for t in (token(part) for part in quote.split()) if t]
    spoken = [(index, token(word.text)) for index, word in enumerate(words)]
    spoken = [(index, t) for index, t in spoken if t]
    if not wanted:
        return None
    for at in range(len(spoken) - len(wanted) + 1):
        if [t for _, t in spoken[at : at + len(wanted)]] == wanted:
            return spoken[at][0], spoken[at + len(wanted) - 1][0]
    return None


def place_graphics(
    picks: Sequence[MotionGraphicPick],
    words: Sequence[CaptionWord],
    length: float,
    max_items: int,
) -> list[PlacedGraphic]:
    """Return the first max_items of picks that can show in a clip whose
    render lasts length seconds and says words (times in milliseconds of
    the rendered clip), placed on their quotes and in time order.

    A pick whose quote is not said, that would be cut shorter than
    SHORTEST_SECONDS by the clip's end, or that overlaps (with
    GAP_SECONDS) a placed pick of its template is left out (logged).
    """
    placed: list[PlacedGraphic] = []
    for pick in picks:
        if len(placed) == max_items:
            break
        found = quote_span(words, pick.quote)
        if found is None:
            logger.info("motion graphic %r left out: quote not said", pick.text)
            continue
        start = words[found[0]].start / 1000
        said_until = words[found[1]].end / 1000
        end = min(max(said_until, start + MIN_SECONDS), start + MAX_SECONDS, length)
        if end - start < SHORTEST_SECONDS:
            logger.info("motion graphic %r left out: the clip ends", pick.text)
            continue
        if any(_clashes(other, pick, start, end) for other in placed):
            logger.info("motion graphic %r left out: it overlaps another", pick.text)
            continue
        placed.append(PlacedGraphic(pick, round(start, 3), round(end, 3)))
    return sorted(placed, key=lambda graphic: graphic.start)


def graphic_props(pick: MotionGraphicPick, style: BrandStyle) -> TextProps:
    """Return the props that draw pick with its template in style: its text
    and then its label, each wrapped to the template's line width, at a
    font size that fits the longest line."""
    lower_third = TEMPLATES[pick.kind] == "lower_third"
    chars = LOWER_THIRD_CHARS if lower_third else CALLOUT_CHARS
    lines = wrap_lines(pick.text, chars, 2) + wrap_lines(pick.label, chars, 1)
    scale = fit_scale(lines, chars)
    text = "\n".join(lines)
    if lower_third:
        return TextProps(
            text=text,
            font=style.font,
            size=round(LOWER_THIRD_SIZE * scale, 4),
            color=LOWER_THIRD_COLOR,
            box=style.color,
            box_opacity=0.9,
            y=LOWER_THIRD_Y,
            animation_in="slide_right",
            animation_out="fade",
            in_seconds=0.35,
            out_seconds=0.3,
        )
    return TextProps(
        text=text,
        font=style.font,
        size=round(CALLOUT_SIZE * scale, 4),
        color=style.color,
        stroke=CALLOUT_STROKE,
        stroke_width=0.1,
        y=CALLOUT_Y,
        animation_in="pop",
        animation_out="fade",
        in_seconds=0.3,
        out_seconds=0.3,
    )


def motion_graphic_items(
    picks: Sequence[MotionGraphicPick],
    words: Sequence[CaptionWord],
    length: float,
    style: BrandStyle,
    max_items: int,
) -> list[TrackItem]:
    """Return the text items of picks (place_graphics) in style, in time
    order, with ids MOTION_ITEM-0, MOTION_ITEM-1, ..."""
    return [
        TrackItem(
            id=f"{MOTION_ITEM}-{index}",
            kind="text",
            start=graphic.start,
            end=graphic.end,
            props=graphic_props(graphic.pick, style).model_dump(),
        )
        for index, graphic in enumerate(place_graphics(picks, words, length, max_items))
    ]


def is_motion_graphic(item: TrackItem) -> bool:
    """Return whether item is a motion graphic (its id is MOTION_ITEM-<n>)."""
    prefix, _, number = item.id.partition("-")
    return prefix == MOTION_ITEM and number.isdigit()


def text_room(items: Sequence[TrackItem]) -> int:
    """Return how many motion graphics fit on a text track of items once
    its motion graphics are replaced (MAX_TEXT_LAYERS less the others)."""
    return max(MAX_TEXT_LAYERS - len(without_motion_graphics(items)), 0)


def without_motion_graphics(items: Sequence[TrackItem]) -> list[TrackItem]:
    """Return the text track items without its motion graphics."""
    return [item for item in items if not is_motion_graphic(item)]


def _clashes(
    other: PlacedGraphic, pick: MotionGraphicPick, start: float, end: float
) -> bool:
    """Return whether pick, from start to end, would overlap other (with
    GAP_SECONDS) and is drawn by the same template."""
    if TEMPLATES[other.pick.kind] != TEMPLATES[pick.kind]:
        return False
    return start < other.end + GAP_SECONDS and other.start < end + GAP_SECONDS
