"""An Instagram Reels post's settings and checks (SPEC-v2 3.10): the post
payload (InstagramPostOptions) mapped to the media container request, the
Reels file rules checked before anything is sent, and the meaning of a
container status and of the account's publishing limit.

Rules verified 2026-11-01 (docs/decisions.md "TASK-141") on
https://developers.facebook.com/docs/instagram-platform/content-publishing,
.../instagram-graph-api/reference/ig-user/media,
.../instagram-graph-api/reference/ig-container and
.../instagram-graph-api/reference/error-codes: Reels are MP4 or MOV, 3 s
to 15 min, at most 300 MB; the caption holds at most 2200 characters, 30
hashtags and 20 @ tags; up to 3 collaborators; thumb_offset (ms) must lie
inside the video; a cover image (cover_url) must be on a public server.
"""

import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from clipforge.campaign_rules import played_length
from clipforge.models import Clip, InstagramPostOptions, instagram_caption_problem
from clipforge.publishers.base import PublishError, clip_caption

REEL_SUFFIXES = (".mp4", ".mov")
MAX_VIDEO_BYTES = 300 * 1024 * 1024
MIN_LENGTH_S = 3.0
MAX_LENGTH_S = 15 * 60.0
# Error subcodes that may pass with time (the post is queued again).
RETRYABLE_SUBCODES = frozenset(
    {2207001, 2207003, 2207008, 2207020, 2207032, 2207042, 2207053}
)
SUBCODE_TEXT = {
    2207001: "Instagram had a server error",
    2207003: "Instagram took too long to take the video",
    2207020: "the upload expired",
    2207026: "the video format is not supported (MP4/MOV, H.264/HEVC, AAC)",
    2207032: "Instagram could not create the post",
    2207042: "the account reached Instagram's limit of API posts per 24 h",
    2207050: "the Instagram account is restricted; resolve it in the Instagram app",
    2207051: "Instagram suspected spam and restricted the post",
    2207053: "an unknown upload error",
    2207057: "the cover frame offset is outside the video",
}


def options_of(payload: dict[str, Any]) -> InstagramPostOptions:
    """Return the post's Instagram options; PublishError (final) if the
    payload is not valid."""
    try:
        return InstagramPostOptions.model_validate(payload)
    except ValidationError as exc:
        fields = "; ".join(
            ".".join(map(str, e["loc"])) or e["msg"] for e in exc.errors()
        )
        raise PublishError(
            f"The Instagram post settings are invalid: {fields}."
        ) from exc


def check_video(path: Path, clip: Clip) -> int:
    """Return the video's size in bytes; PublishError (final) if Instagram
    would not take it as a reel (type, size, length)."""
    if path.suffix.lower() not in REEL_SUFFIXES:
        raise PublishError("Instagram takes MP4 or MOV reels only.")
    size = path.stat().st_size
    if size == 0:
        raise PublishError("The rendered video is empty; render it again.")
    if size > MAX_VIDEO_BYTES:
        raise PublishError("Instagram takes reels of at most 300 MB.")
    length = played_length(clip)
    if not MIN_LENGTH_S <= length <= MAX_LENGTH_S:
        raise PublishError(
            f"The clip is {length:g} s; Instagram reels last 3 s to 15 min."
        )
    return size


def container_body(options: InstagramPostOptions, clip: Clip) -> dict[str, Any]:
    """Return the media container request of a reel uploaded from this
    machine (upload_type resumable); PublishError (final) if the caption
    or the cover offset would be refused."""
    caption = (
        options.caption if options.caption is not None else clip_caption(clip)
    ).strip()
    problem = instagram_caption_problem(caption)
    if problem:
        raise PublishError(f"Instagram would refuse the post: {problem}.")
    body: dict[str, Any] = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "share_to_feed": options.share_to_feed,
    }
    if options.collaborators:
        body["collaborators"] = options.collaborators
    if options.thumb_offset_ms is not None:
        if options.thumb_offset_ms >= played_length(clip) * 1000:
            raise PublishError(
                "The cover frame (thumb_offset_ms) is after the end of the clip."
            )
        body["thumb_offset"] = options.thumb_offset_ms
    if options.audio_name:
        body["audio_name"] = options.audio_name
    if options.ai_generated:
        body["is_ai_generated"] = True
    if options.trial_strategy is not None:
        body["trial_params"] = {"graduation_strategy": options.trial_strategy}
    return body


def status_failure(status_code: str, status: str) -> PublishError:
    """Return the PublishError of a container that ended as ERROR or
    EXPIRED (status: Instagram's detail, e.g. an error subcode)."""
    if status_code == "EXPIRED":
        return PublishError(
            "The Instagram upload expired before it was published.", retryable=True
        )
    found = re.search(r"\b(\d{7})\b", status)
    subcode = int(found.group(1)) if found else None
    text = SUBCODE_TEXT.get(subcode or 0) or status.strip() or "no reason given"
    return PublishError(
        f"Instagram did not publish the reel: {text}.",
        retryable=subcode in RETRYABLE_SUBCODES,
    )


def publishing_limit(answer: dict[str, Any]) -> tuple[int, int] | None:
    """Return (posts used, posts allowed) of a content_publishing_limit
    answer, or None if it does not say."""
    rows = answer.get("data")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    used = rows[0].get("quota_usage")
    settings = rows[0].get("config")
    total = settings.get("quota_total") if isinstance(settings, dict) else None
    if isinstance(used, int) and isinstance(total, int):
        return used, total
    return None
