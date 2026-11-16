"""A post's payload built from what it says (PostText) on its platform
(SPEC-v2 3.10), checked against the platform's limits before it is saved.

    youtube    title, description (text + link + hashtags), tags, privacy
    tiktok     caption (title + text + link + hashtags), privacy_level
    instagram  caption (title + text + link + hashtags), collaborators
    facebook   title, description (text + link + hashtags),
               collaborator_page_ids

A field of PostText left None takes the clip's own (the hashtags with the
required ones, first: a text that lists its own hashtags is the owner's).
Collaborator tags are refused on the platforms whose API has none (YouTube,
TikTok); Instagram and Facebook publish publicly, so only "public" (or no
privacy) is taken there. The limits are the ones the publishers verified
(youtube_metadata, tiktok_post, models.instagram_caption_problem); a payload
over a limit is refused rather than cut. The PostText is kept in the payload under
TEXT_KEY so the post can be edited again (the platform's options model
ignores the key).
"""

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from clipforge.models import (
    TIKTOK_CAPTION_MAX,
    Clip,
    FacebookPostOptions,
    InstagramPostOptions,
    PostText,
    SocialPlatform,
    TikTokPostOptions,
    YouTubePostOptions,
)
from clipforge.publishers.base import hashtag_line
from clipforge.publishers.youtube_metadata import DESCRIPTION_MAX_BYTES, fit_tags
from clipforge.required_tags import merge_tags

TEXT_KEY = "text"
OPTIONS: dict[SocialPlatform, type[BaseModel]] = {
    "youtube": YouTubePostOptions,
    "tiktok": TikTokPostOptions,
    "instagram": InstagramPostOptions,
    "facebook": FacebookPostOptions,
}
# The platforms whose post has a title of its own.
TITLED: frozenset[SocialPlatform] = frozenset({"youtube", "facebook"})
COLLABORATOR_KEYS: dict[SocialPlatform, str] = {
    "instagram": "collaborators",
    "facebook": "collaborator_page_ids",
}
PRIVACY_KEYS: dict[SocialPlatform, str] = {
    "youtube": "privacy",
    "tiktok": "privacy_level",
}
PUBLIC_ONLY = frozenset({"instagram", "facebook"})
# The keys that PostText fills; options may not set them.
TEXT_FIELDS = frozenset(
    {"title", "description", "caption", "tags", "privacy", "privacy_level"}
    | set(COLLABORATOR_KEYS.values())
)


class PayloadInvalid(ValueError):
    """The post cannot be made on its platform; message says why."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def build_payload(
    platform: SocialPlatform,
    text: PostText,
    clip: Clip,
    required: Sequence[str] = (),
) -> dict[str, Any]:
    """Return the payload of clip's post on platform saying text, whose
    default hashtags are the required ones and the clip's; PayloadInvalid
    if the platform cannot take it."""
    model = OPTIONS.get(platform)
    if model is None:
        raise PayloadInvalid(f"ClipForge cannot post to {platform} yet.")
    unknown = set(text.options) - (set(model.model_fields) - TEXT_FIELDS)
    if unknown:
        raise PayloadInvalid(f"{platform} has no option {', '.join(sorted(unknown))}.")
    native = {**text.options, **_text_fields(platform, text, clip, required)}
    try:
        options = model.model_validate(native)
    except ValidationError as exc:
        raise PayloadInvalid(_errors(platform, exc)) from exc
    native = options.model_dump(mode="json", include=set(native))
    problem = _limit_problem(platform, native)
    if problem:
        raise PayloadInvalid(f"{_name(platform)}: {problem}.")
    return {**native, TEXT_KEY: text.model_dump(mode="json")}


def text_of(payload: dict[str, Any]) -> PostText:
    """Return the PostText a payload was built from (empty if none)."""
    return PostText.model_validate(payload.get(TEXT_KEY) or {})


def ready_problem(platform: SocialPlatform, payload: dict[str, Any]) -> str | None:
    """Return what the post still needs before it may be published (e.g.
    TikTok's privacy level), or None."""
    if platform == "tiktok" and not payload.get("privacy_level"):
        return "Choose who can see the TikTok post (privacy) before publishing."
    return None


def _text_fields(
    platform: SocialPlatform, text: PostText, clip: Clip, required: Sequence[str]
) -> dict[str, Any]:
    """Return the platform's text keys (title, caption, tags, privacy,
    collaborators) for text, the clip's own where text has none."""
    title = (clip.title if text.title is None else text.title).strip()
    hashtags = (
        merge_tags(required, clip.hashtags) if text.hashtags is None else text.hashtags
    )
    caption = clip.description if text.caption is None else text.caption
    if platform not in TITLED:
        caption = _join(title, caption)
    body = _join(caption, text.link or "", hashtag_line(hashtags))
    fields: dict[str, Any] = {}
    if platform in TITLED:
        fields |= {"title": title, "description": body}
    else:
        fields["caption"] = body
    if platform == "youtube":
        fields["tags"] = [
            tag.strip().lstrip("#") for tag in hashtags if tag.strip("# ")
        ]
    fields |= _privacy(platform, text.privacy)
    if text.collaborators:
        key = COLLABORATOR_KEYS.get(platform)
        if key is None:
            raise PayloadInvalid(f"{_name(platform)} posts take no collaborator tags.")
        fields[key] = text.collaborators
    return fields


def _privacy(platform: SocialPlatform, privacy: str | None) -> dict[str, Any]:
    """Return the platform's privacy key for privacy (None: its default)."""
    if platform in PUBLIC_ONLY:
        if privacy not in (None, "public"):
            raise PayloadInvalid(f"{_name(platform)} posts are always public.")
        return {}
    key = PRIVACY_KEYS[platform]
    return {} if privacy is None else {key: privacy}


def _limit_problem(platform: SocialPlatform, payload: dict[str, Any]) -> str | None:
    """Return the platform limit the payload goes over, or None (the
    options model checked the others)."""
    if platform == "youtube":
        return _youtube_problem(payload)
    if platform == "tiktok":
        units = len(payload["caption"].encode("utf-16-le")) // 2
        if units > TIKTOK_CAPTION_MAX:
            return f"the caption has more than {TIKTOK_CAPTION_MAX} characters"
    return None


def _youtube_problem(payload: dict[str, Any]) -> str | None:
    """YouTube: a title, no "<" or ">", a description of at most 5000
    bytes and tags of at most 500 characters."""
    title, description = payload["title"], payload["description"]
    if not title:
        return "the video needs a title"
    if any(char in title + description for char in "<>"):
        return 'the title and description cannot contain "<" or ">"'
    if len(description.encode()) > DESCRIPTION_MAX_BYTES:
        return f"the description is over {DESCRIPTION_MAX_BYTES} bytes"
    unique = {" ".join(tag.split()).casefold() for tag in payload["tags"]}
    if len(fit_tags(payload["tags"])) < len(unique):
        return "the tags are over 500 characters"
    return None


def _errors(platform: SocialPlatform, exc: ValidationError) -> str:
    """Return the validation errors as one sentence."""
    details = "; ".join(
        f"{'.'.join(map(str, error['loc'])) or 'post'}: {error['msg']}"
        for error in exc.errors()
    )
    return f"{_name(platform)}: {details}."


def _join(*parts: str) -> str:
    """Return the non-blank parts, stripped, as paragraphs."""
    return "\n\n".join(part.strip() for part in parts if part.strip())


def _name(platform: SocialPlatform) -> str:
    return {"youtube": "YouTube", "tiktok": "TikTok"}.get(platform, platform.title())
