"""The daily digest (SPEC-v2 3.17 and 3.19): one notification a day, from the
configured time of day, that sums up what the owner has to do or look at:
the drafts waiting in the approval inbox, the posts scheduled for today, the
published posts not submitted on their campaign board yet, and the earnings
estimated for yesterday.

The estimate is approved_views / 1000 * the campaign's rate, of the
submissions whose board answer or numbers the owner entered yesterday
(Submission.answered_at); there are no per-day views to count yet, so it is a
rough figure and is labeled as an estimate. A digest with nothing in it is not
sent. send_due() is called by Auto Import's tick; a day gets one digest
(dedupe_key), even if the app runs again.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, tzinfo

from sqlalchemy import Engine, func
from sqlmodel import Session, col, select

from clipforge import config, notifications, submissions
from clipforge.autopilot.rows import DraftRow
from clipforge.campaign_rows import CampaignRow
from clipforge.models import Notification
from clipforge.social_rows import PostRow
from clipforge.submission_rows import SubmissionRow
from clipforge.watch.times import utc_now

logger = logging.getLogger(__name__)
INBOX_LINK = "/inbox"
# The statuses of a post that is (or was) due on its day.
SCHEDULED_STATUSES = ("queued", "uploading", "published")
EARNING_STATUSES = ("approved", "paid")


@dataclass(frozen=True)
class Digest:
    """The numbers of a digest; earnings_yesterday is in USD."""

    drafts_waiting: int
    posts_today: int
    submissions_pending: int
    earnings_yesterday: float

    @property
    def empty(self) -> bool:
        """Whether there is nothing to tell."""
        return not (
            self.drafts_waiting
            or self.posts_today
            or self.submissions_pending
            or self.earnings_yesterday
        )


def _day_bounds(day_start: datetime, days: int = 1) -> tuple[datetime, datetime]:
    """Return the UTC start of the local day that starts at day_start and the
    start of the day `days` days later."""
    start = day_start.astimezone(UTC)
    return start, (day_start + timedelta(days=days)).astimezone(UTC)


def build(engine: Engine, now: datetime, tz: tzinfo | None = None) -> Digest:
    """Return the digest at now: the days are those of the timezone tz (the
    computer's, by default)."""
    local = now.astimezone(tz)
    today = datetime.combine(local.date(), time.min, tzinfo=local.tzinfo)
    yesterday = today - timedelta(days=1)
    today_from, today_to = _day_bounds(today)
    yesterday_from, yesterday_to = _day_bounds(yesterday)
    submissions.sync(engine)
    with Session(engine) as session:
        drafts = session.exec(
            select(func.count()).where(col(DraftRow.status) == "pending")
        ).one()
        posts = session.exec(
            select(func.count()).where(
                col(PostRow.status).in_(SCHEDULED_STATUSES),
                col(PostRow.scheduled_at) >= today_from,
                col(PostRow.scheduled_at) < today_to,
            )
        ).one()
        pending = session.exec(
            select(func.count()).where(col(SubmissionRow.status) == "not_submitted")
        ).one()
        answered = session.exec(
            select(SubmissionRow.approved_views, CampaignRow.rate_per_1k_usd)
            .join(CampaignRow, col(CampaignRow.id) == SubmissionRow.campaign_id)
            .where(
                col(SubmissionRow.status).in_(EARNING_STATUSES),
                col(SubmissionRow.approved_views).is_not(None),
                col(CampaignRow.rate_per_1k_usd).is_not(None),
                col(SubmissionRow.answered_at) >= yesterday_from,
                col(SubmissionRow.answered_at) < yesterday_to,
            )
        ).all()
    earnings = sum(views * rate / 1000 for views, rate in answered if views and rate)
    return Digest(drafts, posts, pending, round(earnings, 2))


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def describe(digest: Digest) -> tuple[str, str]:
    """Return the title and the body (one line per number) of the digest."""
    title = "Your daily digest"
    if digest.drafts_waiting:
        title = f"{_count(digest.drafts_waiting, 'draft')} waiting for you"
    lines = [
        f"Drafts waiting for approval: {digest.drafts_waiting}",
        f"Posts scheduled today: {digest.posts_today}",
        f"Submissions still to do: {digest.submissions_pending}",
        f"Estimated earnings yesterday: ${digest.earnings_yesterday:.2f} (estimate)",
    ]
    return title, "\n".join(lines)


def due_time(text: str) -> time | None:
    """Return the digest time of day from digest_time ("HH:MM"), None if the
    digest is off."""
    return time.fromisoformat(text) if text else None


def send_due(
    engine: Engine, now: datetime | None = None, tz: tzinfo | None = None
) -> Notification | None:
    """Send today's digest as a notification (and by email and to the desktop
    if those are on) if digest_time has passed at now (default: the current
    time) and it was not sent today; return it. None if there is no digest
    time, it is not time yet, today's was sent or there is nothing to tell."""
    at = due_time(config.settings.digest_time)
    moment = utc_now() if now is None else now
    local = moment.astimezone(tz)
    if at is None or local.time() < at:
        return None
    digest = build(engine, moment, tz)
    if digest.empty:
        return None
    title, body = describe(digest)
    return notifications.notify(
        engine,
        "digest",
        title,
        body,
        INBOX_LINK,
        dedupe_key=f"digest:{local.date().isoformat()}",
    )
