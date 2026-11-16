"""The limits and style of a post on each platform, and the cutting of the
LLM's text to them (SPEC-v2 3.10; docs/decisions.md, TASK-148).

    youtube    title <= 100 characters, description <= 5000 bytes (UTF-8,
               hashtags included), tags <= 500 characters
    tiktok     caption <= 2200 UTF-16 units (title + text + hashtags)
    instagram  caption <= 2200 characters and 30 hashtags (title + text +
               hashtags)
    facebook   title and description: no documented limit; ClipForge keeps
               to 100 characters and 2200 characters like the others

The LLM is asked to stay within them, but its reply is cut here rather than
trusted: a cut text ends with "…" at a word boundary. The hashtags go
after the text in every payload (post_payload), so their line is taken off
the text's budget.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from clipforge.models import CopyPlatform, PostCopy
from clipforge.publishers.base import hashtag_line
from clipforge.publishers.youtube_metadata import DESCRIPTION_MAX_BYTES, fit_tags
from clipforge.required_tags import merge_tags

ELLIPSIS = "…"
PARAGRAPH = "\n\n"
INSTAGRAM_HASHTAGS_MAX = 30
HEADLINE_MAX = 70


def utf8_bytes(text: str) -> int:
    """Return the size of text in UTF-8 bytes."""
    return len(text.encode())


def utf16_units(text: str) -> int:
    """Return the length of text in UTF-16 code units (TikTok's count)."""
    return len(text.encode("utf-16-le")) // 2


@dataclass(frozen=True)
class PlatformStyle:
    """What a platform's post looks like: its name, whether it has a title of its
    own (else a headline starts the caption), the longest title or
    headline, the longest text (in the units of measure), the usual number
    of hashtags (fewest, most), the most it takes and a style note for the
    LLM."""

    platform: CopyPlatform
    name: str
    titled: bool
    title_max: int
    text_max: int
    measure: Callable[[str], int]
    unit: str
    tags: tuple[int, int]
    tags_max: int
    note: str


STYLES: dict[CopyPlatform, PlatformStyle] = {
    "youtube": PlatformStyle(
        platform="youtube",
        name="YouTube Shorts",
        titled=True,
        title_max=100,
        text_max=DESCRIPTION_MAX_BYTES,
        measure=utf8_bytes,
        unit="bytes",
        tags=(3, 5),
        tags_max=15,
        note=(
            "A searchable title that names the topic or the punchline. The "
            "description is one to three short sentences."
        ),
    ),
    "tiktok": PlatformStyle(
        platform="tiktok",
        name="TikTok",
        titled=False,
        title_max=HEADLINE_MAX,
        text_max=2200,
        measure=utf16_units,
        unit="UTF-16 units",
        tags=(3, 5),
        tags_max=15,
        note=(
            "A short, hooky caption: the headline is its first line, "
            "followed by one or two short lines. Informal, easy to read."
        ),
    ),
    "instagram": PlatformStyle(
        platform="instagram",
        name="Instagram Reels",
        titled=False,
        title_max=HEADLINE_MAX,
        text_max=2200,
        measure=len,
        unit="characters",
        tags=(5, 10),
        tags_max=INSTAGRAM_HASHTAGS_MAX,
        note=(
            "A caption with a strong first line (only its start shows "
            "before 'more'), then a few short lines and a call to follow "
            "or comment."
        ),
    ),
    "facebook": PlatformStyle(
        platform="facebook",
        name="Facebook Reels",
        titled=True,
        title_max=100,
        text_max=2200,
        measure=len,
        unit="characters",
        tags=(2, 4),
        tags_max=10,
        note=(
            "A plain, friendly title and a description that invites "
            "people to watch and share."
        ),
    ),
}


def hashtag_count(style: PlatformStyle, change: str | None) -> tuple[int, int]:
    """Return how many hashtags to write (fewest, most): the platform's
    usual number, or more or fewer of them ("none" is 0, 0)."""
    low, high = style.tags
    if change == "more":
        return high, min(high + 3, style.tags_max)
    if change == "fewer":
        return 1, max(1, low - 1)
    if change == "none":
        return 0, 0
    return low, high


def cut(text: str, limit: int, measure: Callable[[str], int]) -> str:
    """Return text, cut at a word boundary and ended with "…" if its
    measure is over limit; "" if even "…" does not fit."""
    text = text.strip()
    if measure(text) <= limit:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if measure(text[:middle].rstrip() + ELLIPSIS) <= limit:
            low = middle
        else:
            high = middle - 1
    head = text[:low]
    space = max(head.rfind(" "), head.rfind("\n"))
    if space > low // 2:
        head = head[:space]
    head = head.rstrip(" \n,;:-")
    return head + ELLIPSIS if head else ""


def fit_tags_for(
    style: PlatformStyle,
    hashtags: list[str],
    most: int,
    required: Sequence[str] = (),
) -> list[str]:
    """Return the required hashtags (always all of them, first) and then at
    most `most` of the hashtags (the platform's most for all together), and
    for YouTube only those that fit its 500 characters of tags."""
    tags = merge_tags(required, hashtags[:most], style.tags_max)
    return fit_tags(tags) if style.platform == "youtube" else tags


def fit_title(style: PlatformStyle, title: str) -> str:
    """Return the title or headline cut to the platform's limit, on one
    line ("<" and ">" are removed for YouTube)."""
    title = " ".join(title.split())
    if style.platform == "youtube":
        title = title.replace("<", "").replace(">", "")
    return cut(title, style.title_max, len)


def fit_caption(
    style: PlatformStyle, caption: str, hashtags: list[str], head: str = ""
) -> str:
    """Return the caption (the description) cut so that head (the title
    in the caption of a platform without titles), the caption and the
    hashtag line together are within the platform's text limit."""
    tags = hashtag_line(hashtags)
    taken = [part for part in (head, tags) if part]
    spent = style.measure(PARAGRAPH.join(taken)) + (len(PARAGRAPH) if taken else 0)
    if style.platform == "youtube":
        caption = caption.replace("<", "").replace(">", "")
    return cut(caption, style.text_max - spent, style.measure)


def compose(
    style: PlatformStyle,
    title: str,
    description: str,
    hashtags: list[str],
    credit: str,
    required: Sequence[str] = (),
) -> PostCopy:
    """Return the post of the LLM's headline and description on the
    platform: the credit line closes the description, and each part is cut
    to the platform's limits (the description first, then the credit's room
    is kept). Platforms without titles carry the headline in the caption.
    The required hashtags come first and are never cut: the description
    gives way to them."""
    title = fit_title(style, title)
    tags = fit_tags_for(style, hashtags, style.tags_max, required)
    head = "" if style.titled else title
    credit = credit.strip()
    spent = _spent(style, head, tags, credit)
    body = cut(description, style.text_max - spent, style.measure)
    if credit and credit not in body:
        body = PARAGRAPH.join(part for part in (body, credit) if part)
    caption = body if style.titled else PARAGRAPH.join(p for p in (head, body) if p)
    return PostCopy(title=title if style.titled else "", caption=caption, hashtags=tags)


def _spent(style: PlatformStyle, head: str, tags: list[str], credit: str) -> int:
    """Return how much of the text limit the headline, the hashtags and the
    credit line take, with the paragraph breaks between all the parts."""
    parts = [part for part in (head, credit, hashtag_line(tags)) if part]
    if not parts:
        return 0
    return style.measure(PARAGRAPH.join(parts)) + len(PARAGRAPH)
