"""Bulk scheduling of posts (SPEC-v2 3.10): every clip to every target
account, each in the account's next free slot of the schedule rules
(scheduler.slots.allocate), around the posts the accounts already have at
a time (drafts and queued). An account's posts per day are also capped by
its platform's daily post limit (DAILY_POSTS).

Every payload is built (and checked) before the first post is saved, so a
refused payload saves nothing; so does a post that before_save refuses
(the caller's publish checks when it queues them). The posts are saved as
drafts with their time; queuing them is the caller's choice (human only,
api.posts).
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import Engine

from clipforge import config, post_payload, post_tags, posts, social_accounts
from clipforge.models import BulkSchedule, Clip, Post, SocialAccount, SocialPlatform
from clipforge.scheduler.slots import AccountTarget, allocate

BeforeSave = Callable[[int, SocialAccount, dict[str, Any]], None]

# Posts per account per day that each platform takes through its API, as
# the publishers record them: YouTube by the project's daily upload quota
# (youtube.UPLOADS), TikTok about 15 per creator (tiktok.py), Instagram 100
# per account (instagram.POSTING_CAP), Facebook 30 reels per Page
# (facebook.py).
DAILY_POSTS: dict[SocialPlatform, Callable[[], int]] = {
    "youtube": lambda: config.settings.youtube_daily_uploads,
    "tiktok": lambda: 15,
    "instagram": lambda: 100,
    "facebook": lambda: 30,
}


def daily_cap(platform: SocialPlatform) -> int | None:
    """Return the platform's posts per account per day (None: no limit)."""
    cap = DAILY_POSTS.get(platform)
    return None if cap is None else cap()


def bulk_schedule(
    engine: Engine,
    body: BulkSchedule,
    clip_of: Callable[[int], Clip],
    now: datetime,
    before_save: BeforeSave | None = None,
) -> list[Post]:
    """Save a draft post with its time for every clip on every target
    account and return them, earliest first. PostNotFound for an unknown
    clip or account, post_payload.PayloadInvalid for a payload the platform
    would refuse, ValueError for a repeated account, slots.NoFreeSlot when
    the posts do not fit in the slots. before_save(clip_id, account,
    payload) runs for every post before any is saved; what it raises
    passes through."""
    accounts: dict[int, SocialAccount] = {}
    for target in body.targets:
        if target.account_id in accounts:
            raise ValueError(f"account {target.account_id} is listed twice")
        try:
            accounts[target.account_id] = social_accounts.get_account(
                engine, target.account_id
            )
        except social_accounts.AccountNotFound as exc:
            raise posts.PostNotFound(str(exc)) from exc
    clips = {clip_id: clip_of(clip_id) for clip_id in body.clip_ids}
    payloads = {
        (clip_id, target.account_id): post_payload.build_payload(
            accounts[target.account_id].platform,
            target.text,
            clip,
            post_tags.required_hashtags(
                engine, clip.project_id, accounts[target.account_id]
            ),
        )
        for clip_id, clip in clips.items()
        for target in body.targets
    }
    if before_save is not None:
        for (clip_id, account_id), payload in payloads.items():
            before_save(clip_id, accounts[account_id], payload)
    targets = [
        AccountTarget(account.id, daily_cap(account.platform))
        for account in accounts.values()
    ]
    busy = posts.scheduled_times(engine, accounts)
    assignments = allocate(body.clip_ids, targets, body.rules, now, busy)
    return [
        posts.create_post(
            engine,
            clip_id=slot.clip_id,
            account_id=slot.account_id,
            payload=payloads[slot.clip_id, slot.account_id],
            scheduled_at=slot.scheduled_at,
        )
        for slot in assignments
    ]
