"""The hashtags that every generated post text carries (steering, owner
request 2026-11-02): the global always_hashtags setting, the extra ones of
the target social account and the campaign's required hashtags.

This module has no ClipForge imports, so config and models can use it.
Tags are kept without "#" and compared in any letter case; the first
spelling stays. Posting code puts the required tags first and never cuts
them: when a platform's limit is hit it shortens the AI's text instead
(post_copy_fit).
"""

import json
import re
from collections.abc import Iterable, Sequence


def clean_tag(value: str) -> str:
    """Return value as a hashtag without "#" or white space ("" if none)."""
    return re.sub(r"[#\s]+", "", value)


def clean_tags(values: Iterable[str]) -> list[str]:
    """Return the hashtags of values without "#", with empty and repeated
    ones (in any letter case) dropped, the first spelling and the order
    kept."""
    seen: dict[str, str] = {}
    for value in values:
        tag = clean_tag(value)
        if tag:
            seen.setdefault(tag.casefold(), tag)
    return list(seen.values())


def merge_tags(
    required: Sequence[str], others: Iterable[str], limit: int | None = None
) -> list[str]:
    """Return the required hashtags, then the others that are not among
    them, no more than limit in all (None: no limit). The required ones are
    all kept, even past limit."""
    must = clean_tags(required)
    taken = {tag.casefold() for tag in must}
    rest = [tag for tag in clean_tags(others) if tag.casefold() not in taken]
    room = len(rest) if limit is None else max(limit - len(must), 0)
    return [*must, *rest[:room]]


def tags_from_text(text: str) -> list[str]:
    """Return the hashtags of text that is a JSON list or separated by
    commas, spaces or "#"."""
    stripped = text.strip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            return clean_tags(str(item) for item in parsed)
    return clean_tags(re.split(r"[,\s]+", stripped))
