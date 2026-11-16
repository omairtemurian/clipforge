"""A Facebook Page reel's settings and checks (SPEC-v2 3.10): the post
payload (FacebookPostOptions) mapped to the publish request, the Reels file
rules checked before anything is sent, and the meaning of a video's status.

Rules verified 2026-11-01 (docs/decisions.md "TASK-142") on
https://developers.facebook.com/docs/video-api/guides/reels-publishing and
https://developers.facebook.com/docs/graph-api/reference/page/video_reels:
a reel is a vertical (9:16) MP4 of 3 to 90 seconds, at least 540x960,
24 to 60 frames per second; the publish call takes video_id, upload_phase
finish, video_state (DRAFT, SCHEDULED, PUBLISHED), description, title and
is_ai_generated. GET /{video-id}?fields=status answers {"status":
{video_status, uploading_phase, processing_phase, publishing_phase}} with
phases {status, error: {message}} and publishing_phase.publish_status
(draft, error, published, scheduled).
"""

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from clipforge.campaign_rules import played_length
from clipforge.models import Clip, FacebookPostOptions
from clipforge.publishers.base import PublishError, clip_caption

REEL_SUFFIXES = (".mp4", ".mov")
MIN_LENGTH_S = 3.0
MAX_LENGTH_S = 90.0
DONE = ("complete", "completed")
# The video_status values after which the video never publishes by itself;
# only a failed or expired upload may be sent again.
FAILED_STATUSES = {"error": False, "upload_failed": True, "expired": True}


def options_of(payload: dict[str, Any]) -> FacebookPostOptions:
    """Return the post's Facebook options; PublishError (final) if the
    payload is not valid."""
    try:
        return FacebookPostOptions.model_validate(payload)
    except ValidationError as exc:
        fields = "; ".join(
            ".".join(map(str, e["loc"])) or e["msg"] for e in exc.errors()
        )
        raise PublishError(
            f"The Facebook post settings are invalid: {fields}."
        ) from exc


def check_video(path: Path, clip: Clip) -> int:
    """Return the video's size in bytes; PublishError (final) if Facebook
    would not take it as a reel (type, length)."""
    if path.suffix.lower() not in REEL_SUFFIXES:
        raise PublishError("Facebook takes MP4 reels only.")
    size = path.stat().st_size
    if size == 0:
        raise PublishError("The rendered video is empty; render it again.")
    length = played_length(clip)
    if not MIN_LENGTH_S <= length <= MAX_LENGTH_S:
        raise PublishError(f"The clip is {length:g} s; Facebook reels last 3 to 90 s.")
    return size


def publish_body(
    options: FacebookPostOptions, clip: Clip, video_id: str
) -> dict[str, Any]:
    """Return the request that ends the upload session of video_id and
    publishes the reel to the Page at once."""
    description = (
        options.description if options.description is not None else clip_caption(clip)
    ).strip()
    body: dict[str, Any] = {
        "video_id": video_id,
        "upload_phase": "finish",
        "video_state": "PUBLISHED",
    }
    if description:
        body["description"] = description
    if options.title and options.title.strip():
        body["title"] = options.title.strip()
    if options.ai_generated:
        body["is_ai_generated"] = True
    return body


def reel_state(answer: dict[str, Any]) -> tuple[str, PublishError | None]:
    """Return how a /{video-id}?fields=status answer says the reel is:
    "published", "failed" (with the PublishError: retryable only if the
    upload may simply be sent again) or "pending"."""
    raw = answer.get("status")
    status = raw if isinstance(raw, dict) else {}
    for name in ("processing_phase", "publishing_phase", "uploading_phase"):
        phase = status.get(name)
        error = (
            (phase.get("error") or phase.get("errors"))
            if isinstance(phase, dict)
            else None
        )
        if error:
            message = error.get("message") if isinstance(error, dict) else error
            return "failed", PublishError(
                "Facebook did not publish the reel: "
                f"{message or 'it reported an error'} ({name.split('_')[0]})."
            )
    video_status = str(status.get("video_status") or "")
    if video_status in FAILED_STATUSES:
        return "failed", PublishError(
            f"Facebook did not publish the reel (video status {video_status}).",
            retryable=FAILED_STATUSES[video_status],
        )
    publishing = status.get("publishing_phase")
    publishing = publishing if isinstance(publishing, dict) else {}
    if publishing.get("publish_status") == "published" or (
        publishing.get("status") in DONE
    ):
        return "published", None
    return "pending", None
