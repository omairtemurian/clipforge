"""The auto headline of a clip (SPEC-v2 3.5): one opening line of text,
written by the LLM (clip_graphics.write_headline) or the owner, drawn over
the first HEADLINE_SECONDS of the render in the project's brand style
(clipforge.brand_style: its font, on a box of its primary color).

The headline is an item of the clip's text track with id HEADLINE_ID, so
the editor moves, restyles and retimes it like any text overlay; it counts
as one of the track's MAX_TEXT_LAYERS. The clip's hook_text keeps its text
(what the post copy and title prompts read), and while the item exists
the captions do not draw hook_text in the caption template's style
(pipeline/captions), so the line shows once.
"""

from collections.abc import Sequence

from clipforge.brand_style import BrandStyle
from clipforge.models import CutRange, SourceSpan, TextProps, Timeline, TrackItem
from clipforge.pipeline.sections import played_spans
from clipforge.pipeline.text_overlay import fit_scale, wrap_lines

# The id of a clip's headline item on its text track.
HEADLINE_ID = "headline"
# How long the headline shows from the clip's start, in seconds.
HEADLINE_SECONDS = 3.0
# Its font size (times the frame's height) and the characters of a line at
# that size: two lines of 20 fit a 9:16 frame's width.
HEADLINE_SIZE = 0.04
HEADLINE_CHARS_PER_LINE, HEADLINE_LINES = 20, 2
# The text color on the brand-colored box, and where the headline sits.
HEADLINE_COLOR = "#FFFFFF"
HEADLINE_Y = 0.12


def headline_props(text: str, style: BrandStyle) -> TextProps:
    """Return the props of a headline that says text in style: white text in
    the brand font on a box of the brand color, near the top, wrapped to at
    most two lines (headline_lines) and sliding down in, fading out."""
    lines = headline_lines(text)
    return TextProps(
        text="\n".join(lines),
        font=style.font,
        size=round(HEADLINE_SIZE * fit_scale(lines, HEADLINE_CHARS_PER_LINE), 4),
        color=HEADLINE_COLOR,
        box=style.color,
        box_opacity=0.95,
        x=0.5,
        y=HEADLINE_Y,
        animation_in="slide_down",
        animation_out="fade",
        in_seconds=0.35,
        out_seconds=0.3,
    )


def headline_lines(text: str) -> list[str]:
    """Return text's words in lines of at most HEADLINE_CHARS_PER_LINE
    characters, at most HEADLINE_LINES lines (wider ones if needed)."""
    return wrap_lines(" ".join(text.split()), HEADLINE_CHARS_PER_LINE, HEADLINE_LINES)


def headline_item(text: str, style: BrandStyle, length: float) -> TrackItem:
    """Return the headline item of a clip whose render lasts length seconds
    (> 0): headline_props(text, style) from 0 to HEADLINE_SECONDS (or the
    clip's end)."""
    props = headline_props(text, style).model_dump()
    end = min(HEADLINE_SECONDS, length)
    return TrackItem(id=HEADLINE_ID, kind="text", start=0, end=end, props=props)


def new_clip_tracks(
    tracks: Timeline,
    span: SourceSpan,
    cut_ranges: Sequence[CutRange],
    hook_text: str,
    style: BrandStyle | None,
    fps: int,
) -> Timeline:
    """Return the tracks of a new clip of span (source seconds) with
    cut_ranges, rendered at fps: tracks with a headline item that says
    hook_text in style (the project's brand) on its text track; tracks as
    they are without a style or text (the captions then draw hook_text), or
    if nothing of the clip plays."""
    start, end = span
    played = played_spans(start, end, [span], cut_ranges, fps)
    length = sum(part_end - part_start for part_start, part_end in played)
    if style is None or not hook_text.strip() or length <= 0:
        return tracks
    return tracks.model_copy(update={"text": [headline_item(hook_text, style, length)]})


def has_headline(tracks: Timeline) -> bool:
    """Return whether tracks' text track holds a headline item."""
    return any(item.id == HEADLINE_ID for item in tracks.text)


def with_headline(
    items: Sequence[TrackItem], text: str, style: BrandStyle, length: float
) -> list[TrackItem]:
    """Return the text track items with a headline that says text: an
    existing headline item keeps its place, times and props (the owner's
    edits) with only its text replaced; else a new headline_item comes
    first."""
    if not any(item.id == HEADLINE_ID for item in items):
        return [headline_item(text, style, length), *items]
    new_text = "\n".join(headline_lines(text))
    return [
        item.model_copy(update={"props": item.props | {"text": new_text}})
        if item.id == HEADLINE_ID
        else item
        for item in items
    ]


def without_headline(items: Sequence[TrackItem]) -> list[TrackItem]:
    """Return the text track items without the headline item."""
    return [item for item in items if item.id != HEADLINE_ID]
