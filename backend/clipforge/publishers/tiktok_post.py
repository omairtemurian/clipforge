"""A TikTok Direct Post's settings (SPEC-v2 3.10): the post payload
(TikTokPostOptions) checked against the creator's latest info and mapped to
TikTok's post_info, and the outcome of the post status.

Rules verified 2026-11-01 (docs/decisions.md "TASK-140") on
https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info,
.../content-posting-api-reference-direct-post,
.../content-posting-api-reference-get-video-status and
.../content-sharing-guidelines: privacy_level must be one of the creator's
privacy_level_options (no default); interactions the creator disabled stay
disabled; a video longer than max_video_post_duration_sec is not sent; the
caption ("title") holds at most 2200 UTF-16 code units; branded content is
never SELF_ONLY.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from clipforge.campaign_rules import played_length
from clipforge.models import TIKTOK_CAPTION_MAX, Clip, TikTokPostOptions
from clipforge.publishers.base import PublishError, PublishResult, clip_caption

PROFILE_URL = "https://www.tiktok.com/@"
# fail_reason values that may pass with time (the post is queued again).
RETRYABLE_REASONS = frozenset({"internal", "spam_risk_too_many_posts"})
FAIL_TEXT = {
    "file_format_check_failed": "the video format is not supported",
    "duration_check_failed": "the video length is not allowed",
    "frame_rate_check_failed": "the frame rate is not 23-60 fps",
    "picture_size_check_failed": "the picture size is not 360-4096 px",
    "internal": "TikTok had an internal error",
    "publish_cancelled": "the post was canceled",
    "auth_removed": "the account removed ClipForge's access",
    "spam_risk_too_many_posts": "the account made too many posts in 24 hours",
    "spam_risk_user_banned_from_posting": "TikTok banned the account from posting",
    "spam_risk_text": "TikTok flagged the caption as spam",
    "spam_risk": "TikTok flagged the post as risky",
}
PRIVACY_TEXT = {
    "PUBLIC_TO_EVERYONE": "everyone",
    "MUTUAL_FOLLOW_FRIENDS": "friends",
    "FOLLOWER_OF_CREATOR": "followers",
    "SELF_ONLY": "only me",
}


@dataclass(frozen=True)
class CreatorInfo:
    """The creator_info query's answer: who posts, the privacy levels the
    account offers, the interactions it disabled and its longest video."""

    username: str
    nickname: str
    privacy_options: tuple[str, ...]
    comment_disabled: bool
    duet_disabled: bool
    stitch_disabled: bool
    max_duration_s: int | None

    @classmethod
    def of(cls, data: dict[str, Any]) -> "CreatorInfo":
        """Read the creator_info data object."""
        options = data.get("privacy_level_options")
        longest = data.get("max_video_post_duration_sec")
        return cls(
            username=str(data.get("creator_username") or ""),
            nickname=str(data.get("creator_nickname") or ""),
            privacy_options=tuple(str(o) for o in options)
            if isinstance(options, list)
            else (),
            comment_disabled=data.get("comment_disabled") is True,
            duet_disabled=data.get("duet_disabled") is True,
            stitch_disabled=data.get("stitch_disabled") is True,
            max_duration_s=longest if isinstance(longest, int) else None,
        )

    def restrictions(self) -> list[str]:
        """Return what this account allows, as the account shows it."""
        found = []
        if "FOLLOWER_OF_CREATOR" in self.privacy_options:
            found.append("The TikTok account is private.")
        if self.privacy_options:
            shown = ", ".join(PRIVACY_TEXT.get(o, o) for o in self.privacy_options)
            found.append(f"Who can see posts of this account: {shown}.")
        if self.max_duration_s is not None:
            found.append(
                f"Longest video this account can post: {self.max_duration_s} s."
            )
        disabled = [
            name
            for name, off in (
                ("comments", self.comment_disabled),
                ("Duets", self.duet_disabled),
                ("Stitches", self.stitch_disabled),
            )
            if off
        ]
        if disabled:
            found.append(f"The account turned off {', '.join(disabled)}.")
        return found


def options_of(payload: dict[str, Any]) -> TikTokPostOptions:
    """Return the post's TikTok options; PublishError (final) if the payload
    is not valid or has no privacy level."""
    try:
        options = TikTokPostOptions.model_validate(payload)
    except ValidationError as exc:
        fields = ", ".join(
            ".".join(map(str, e["loc"])) or e["msg"] for e in exc.errors()
        )
        raise PublishError(f"The TikTok post settings are invalid: {fields}.") from exc
    if options.privacy_level is None:
        raise PublishError(
            "Choose who can see the TikTok post (privacy level) before publishing."
        )
    return options


def post_info(
    options: TikTokPostOptions, clip: Clip, creator: CreatorInfo
) -> dict[str, Any]:
    """Return the post_info of the init request; PublishError (final) if the
    account does not offer the privacy level or the clip is too long."""
    privacy = options.privacy_level
    if privacy not in creator.privacy_options:
        offered = ", ".join(creator.privacy_options) or "none"
        raise PublishError(
            f"This TikTok account cannot post as {privacy}; it offers: {offered}."
        )
    length = played_length(clip)
    if creator.max_duration_s is not None and length > creator.max_duration_s:
        raise PublishError(
            f"The clip is {length:g} s; this TikTok account posts at most "
            f"{creator.max_duration_s} s."
        )
    caption = options.caption if options.caption is not None else clip_caption(clip)
    info: dict[str, Any] = {
        "title": fit_utf16(caption.strip(), TIKTOK_CAPTION_MAX),
        "privacy_level": privacy,
        "disable_comment": not options.allow_comment or creator.comment_disabled,
        "disable_duet": not options.allow_duet or creator.duet_disabled,
        "disable_stitch": not options.allow_stitch or creator.stitch_disabled,
        "brand_content_toggle": options.branded_content,
        "brand_organic_toggle": options.brand_organic,
        "is_aigc": options.ai_generated,
    }
    if options.cover_timestamp_ms is not None:
        info["video_cover_timestamp_ms"] = options.cover_timestamp_ms
    return info


def result_of(
    publish_id: str, status: dict[str, Any] | None, username: str
) -> PublishResult:
    """Return the published post: TikTok's public post id and link once
    moderation made it public, else the publish_id (private posts never
    get a post id)."""
    ids = (status or {}).get("publicaly_available_post_id") or (status or {}).get(
        "publicly_available_post_id"
    )
    if isinstance(ids, list) and ids:
        post_id = str(ids[0])
        url = f"{PROFILE_URL}{username}/video/{post_id}" if username else None
        return PublishResult(post_id, url)
    return PublishResult(publish_id, None)


def failure(reason: str) -> PublishError:
    """Return the PublishError of a FAILED post status."""
    text = FAIL_TEXT.get(reason, "no reason given")
    return PublishError(
        f"TikTok did not publish the video: {text} ({reason or 'unknown'}).",
        retryable=reason in RETRYABLE_REASONS,
    )


def fit_utf16(text: str, limit: int) -> str:
    """Return text cut to at most limit UTF-16 code units (whole
    characters)."""
    used = 0
    for index, char in enumerate(text):
        used += 2 if ord(char) > 0xFFFF else 1
        if used > limit:
            return text[:index].rstrip()
    return text
