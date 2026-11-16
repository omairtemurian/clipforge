"""The text of a post written by the LLM per platform (SPEC-v2 3.10,
POST /clips/{id}/post-copy): a title, a description and hashtags in the
style of the platform, within its limits.

The system prompt is prompts/post_copy.md with the JSON Schema of the reply;
the user message names the platform and its limits and holds the clip's
words (as its render shows them), hook, project credit line, current text
and what to write. The reply is cut to the platform's limits
(post_copy_fit); an invalid reply is sent back with its errors, as curate
does. "Rewrite with AI" gives a tone and/or format (which rewrite the title
and the description) or a hashtag change (which only changes the hashtags;
"none" needs no LLM).

The required hashtags (post_tags: the always_hashtags setting, the account's
and the campaign's) come first in every post this writes, are never cut and
are never counted among the AI's: a rewrite that wants fewer or no hashtags
keeps them, and a platform limit shortens the AI's text instead.
"""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from clipforge.clip_text import clip_words
from clipforge.llm import LLMClient, reply_json
from clipforge.models import (
    Clip,
    PostCopy,
    PostCopyReply,
    PostCopyRequest,
    PostTagsReply,
    PostTextReply,
)
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, describe_errors, fill
from clipforge.post_copy_fit import (
    STYLES,
    PlatformStyle,
    compose,
    fit_caption,
    fit_tags_for,
    hashtag_count,
)

logger = logging.getLogger(__name__)

PROMPT = PROMPTS_DIR / "post_copy.md"


class PostCopyError(RuntimeError):
    """The LLM sent no valid post text for a clip."""


def wanted(request: PostCopyRequest) -> tuple[bool, bool]:
    """Return (text, tags): whether the LLM is to write a new title and
    description, and new hashtags. Without options both; a tone or format
    only the text; "more" or "fewer" hashtags only the hashtags ("none"
    needs no LLM)."""
    plain = not (request.tone or request.format or request.hashtags)
    text = plain or bool(request.tone or request.format)
    return text, plain or request.hashtags in ("more", "fewer")


def reply_model(text: bool, tags: bool) -> type[BaseModel]:
    """Return the model of the reply that asks for text and/or tags."""
    if text and tags:
        return PostCopyReply
    return PostTextReply if text else PostTagsReply


def system_prompt(model: type[BaseModel]) -> str:
    """Return the system prompt: post_copy.md with the reply's JSON Schema."""
    return fill(PROMPT, {"schema": json.dumps(model.model_json_schema(), indent=2)})


def user_prompt(
    style: PlatformStyle,
    request: PostCopyRequest,
    clip: Clip,
    words: str,
    credit: str,
    errors: str | None = None,
    required: Sequence[str] = (),
) -> str:
    """Return the user message: the platform and what to write for it, the
    clip's words, hook and current text, the credit line, the hashtags that
    are added anyway, and the errors of the previous reply if it was not
    valid."""
    text, tags = wanted(request)
    current = request.current or PostCopy(
        title=clip.title, caption=clip.description, hashtags=clip.hashtags
    )
    lines = [
        f"Platform: {style.name}. {style.note}",
        f"Write: {_what(style, text, tags)}.",
    ]
    if text:
        lines.append(_limits(style))
    if request.tone:
        lines.append(f"Tone: {request.tone}")
    if request.format:
        lines.append(f"Format: {request.format}")
    if tags:
        low, high = hashtag_count(style, request.hashtags)
        lines.append(f"Hashtags: {low} to {high}")
    if credit and text:
        lines.append(f"A credit line is added after the description: {credit}")
    if required:
        line = " ".join(f"#{tag}" for tag in required)
        lines.append(
            f"These hashtags are added after your text anyway; do not write "
            f"them or count them: {line}"
        )
    body = "\n".join(lines)
    context = (
        f"What is said in the clip:\n{words or '(nothing)'}\n\n"
        f"Hook: {clip.hook_text}\n"
        f"Current title: {current.title or clip.title}\n"
        f"Current description: {current.caption}\n"
        f"Current hashtags: {', '.join(current.hashtags)}"
    )
    message = f"{body}\n\n{context}"
    if errors is None:
        return message
    return (
        f"{message}\n\nYour previous reply was not valid:\n{errors}\n\n"
        "Reply again with only the JSON object described in the instructions."
    )


def write_copy(
    llm: LLMClient,
    request: PostCopyRequest,
    clip: Clip,
    work: Path,
    credit: str,
    required: Sequence[str] = (),
) -> PostCopy:
    """Return the post of clip on request's platform: new title, caption
    and hashtags, or only what the request's options change (the rest is
    request.current's), within the platform's limits. The required hashtags
    are in the post, first, whatever the options.

    An invalid reply is sent back with its errors up to MAX_RETRIES times.
    Raises PostCopyError if no reply was valid, LLMError if the LLM cannot
    be reached, and StepError if the clip's transcript is missing.
    """
    style = STYLES[request.platform]
    text, tags = wanted(request)
    _, most = hashtag_count(style, request.hashtags)
    current = request.current
    if not text and not tags:
        assert current is not None
        return _tags_only(style, current, fit_tags_for(style, [], 0, required))
    words = clip_words(work, clip)
    reply = _ask(llm, style, request, clip, words, credit, required)
    new = fit_tags_for(style, reply.tags, most, required)
    if reply.text is None:
        assert current is not None
        return _tags_only(style, current, new)
    base = current.hashtags if current else clip.hashtags
    kept = new if tags else ([] if request.hashtags == "none" else base)
    return compose(
        style, reply.text.title, reply.text.description, kept, credit, required
    )


@dataclass(frozen=True)
class Reply:
    """A valid reply: its headline and description (None if only hashtags
    were asked for) and its hashtags."""

    text: PostTextReply | None
    tags: list[str]


def _ask(
    llm: LLMClient,
    style: PlatformStyle,
    request: PostCopyRequest,
    clip: Clip,
    words: str,
    credit: str,
    required: Sequence[str],
) -> Reply:
    """Ask llm for what request wants until a reply is valid."""
    model = reply_model(*wanted(request))
    system = system_prompt(model)
    errors = None
    for attempt in range(1, MAX_RETRIES + 2):
        reply = llm.complete_json(
            system, user_prompt(style, request, clip, words, credit, errors, required)
        )
        try:
            return _parsed(model.model_validate_json(reply_json(reply)))
        except ValidationError as exc:
            errors = describe_errors(exc)
            logger.warning(
                "clip %d: %s copy reply %d of %d is not valid:\n%s",
                clip.id,
                request.platform,
                attempt,
                MAX_RETRIES + 1,
                errors,
            )
    raise PostCopyError(
        f"the LLM sent no valid {style.name} text for clip {clip.id} "
        f"in {MAX_RETRIES + 1} tries"
    )


def _parsed(reply: BaseModel) -> Reply:
    """Return the validated reply as a Reply."""
    text = reply if isinstance(reply, PostTextReply) else None
    return Reply(text=text, tags=list(getattr(reply, "hashtags", [])))


def _tags_only(style: PlatformStyle, current: PostCopy, tags: list[str]) -> PostCopy:
    """Return current with the new hashtags, its caption cut if their line
    no longer leaves it room."""
    caption = fit_caption(style, current.caption, tags)
    return PostCopy(title=current.title, caption=caption, hashtags=tags)


def _what(style: PlatformStyle, text: bool, tags: bool) -> str:
    """Name the parts to write."""
    head = "title" if style.titled else "headline"
    parts = [f"a {head} and a description"] if text else []
    return " and ".join(parts + (["hashtags"] if tags else []))


def _limits(style: PlatformStyle) -> str:
    """State the limits of the title or headline and of the description."""
    head = "Title" if style.titled else "Headline"
    return (
        f"Limits: the {head.lower()} at most {style.title_max} characters; the "
        f"description, with hashtags, at most {style.text_max} {style.unit}, "
        "but shorter is better."
    )
