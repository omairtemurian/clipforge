"""The YouTube video resource of a post (SPEC-v2 3.10): its payload
(YouTubePostOptions) and clip mapped to snippet (title, description, tags,
categoryId) and status (privacyStatus, publishAt, selfDeclaredMadeForKids,
containsSyntheticMedia).

Limits verified 2026-11-01 on
https://developers.google.com/youtube/data/reference/rest/v3/videos:
title at most 100 characters and description at most 5000 bytes, both
without "<" or ">"; tags at most 500 characters, where the commas between
tags count and a tag with a space counts as if quoted; publishAt (ISO 8601)
only with privacyStatus private.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from clipforge.models import YOUTUBE_TITLE_MAX, Clip, YouTubePostOptions
from clipforge.publishers.base import PublishError

DESCRIPTION_MAX_BYTES = 5000
TAGS_MAX_CHARS = 500
FORBIDDEN = str.maketrans("", "", "<>")


def options_of(payload: dict[str, Any]) -> YouTubePostOptions:
    """Return the post's YouTube options; PublishError (final) if the
    payload is not valid."""
    try:
        return YouTubePostOptions.model_validate(payload)
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, e["loc"])) for e in exc.errors())
        raise PublishError(f"The YouTube post settings are invalid: {fields}.") from exc


def video_resource(
    options: YouTubePostOptions,
    clip: Clip,
    scheduled_at: datetime | None,
    now: datetime,
) -> dict[str, Any]:
    """Return the video resource (snippet and status) that the upload sends;
    a public post scheduled after now goes up private with publishAt."""
    title = _clean(options.title if options.title is not None else clip.title)
    title = title.strip()[:YOUTUBE_TITLE_MAX].strip()
    if not title:
        raise PublishError("A YouTube video needs a title.")
    tags = options.tags if options.tags is not None else clip.hashtags
    description = (
        options.description
        if options.description is not None
        else _default_description(clip)
    )
    status: dict[str, Any] = {
        "privacyStatus": options.privacy,
        "selfDeclaredMadeForKids": options.made_for_kids,
        "containsSyntheticMedia": options.synthetic_media,
    }
    publish_at = _aware(scheduled_at) if scheduled_at is not None else None
    if options.privacy == "public" and publish_at is not None and publish_at > now:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    snippet: dict[str, Any] = {
        "title": title,
        "description": _fit_bytes(_clean(description), DESCRIPTION_MAX_BYTES),
        "categoryId": options.category_id,
    }
    fitted = fit_tags(tags)
    if fitted:
        snippet["tags"] = fitted
    return {"snippet": snippet, "status": status}


def fit_tags(tags: list[str]) -> list[str]:
    """Return the tags (without "#", "<", ">", blanks and repeats) that fit
    TAGS_MAX_CHARS as YouTube counts them, in order."""
    kept: list[str] = []
    seen: set[str] = set()
    used = 0
    for raw in tags:
        tag = " ".join(_clean(raw).lstrip("#").split())
        if not tag or tag.casefold() in seen:
            continue
        cost = len(tag) + (2 if " " in tag else 0) + (1 if kept else 0)
        if used + cost > TAGS_MAX_CHARS:
            break
        kept.append(tag)
        seen.add(tag.casefold())
        used += cost
    return kept


def _default_description(clip: Clip) -> str:
    """Return the clip's description followed by its hashtags."""
    hashtags = " ".join(f"#{tag}" for tag in clip.hashtags if tag.strip())
    return "\n\n".join(part for part in (clip.description.strip(), hashtags) if part)


def _clean(text: str) -> str:
    """Return text without the characters YouTube refuses ("<", ">")."""
    return text.translate(FORBIDDEN)


def _fit_bytes(text: str, limit: int) -> str:
    """Return text cut to at most limit UTF-8 bytes (whole characters)."""
    data = text.encode()
    if len(data) <= limit:
        return text
    return data[:limit].decode(errors="ignore").rstrip()


def _aware(moment: datetime) -> datetime:
    """Return moment with a time zone (a naive one is UTC)."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
