"""The safety switches of the autopilot (SPEC-v2 3.19).

A campaign's autopilot that is on still makes no drafts while it is stopped
(stop_reason): the owner paused every autopilot (set_paused, the global
"Pause all autopilot"), the campaign's permission evidence is missing, the
campaign is paused or ended, its end date passed, or the day's drafts
already fill its daily quota (max_posts_per_day). Each of these lifts by
itself once the cause is gone. check() also alerts the owner, once a day per
campaign and cause (not for the owner's own pause).

When AUTOPILOT_FAILURES_TO_STOP uploads of a campaign in a row fail
(after_failed_job), its autopilot is turned off and the owner alerted; it
stays off until the owner turns it on again.

Drafts that wait longer than their campaign's draft_ttl_days expire
(expire_drafts, called by Auto Import's tick), paused or not: fresh clips
matter.
"""

import logging
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Engine, update
from sqlmodel import Session, col, select

from clipforge import notifications
from clipforge.autopilot.rows import AutopilotPauseRow, AutopilotSettingsRow, DraftRow
from clipforge.autopilot.settings import get_settings
from clipforge.campaign_rows import CampaignRow
from clipforge.campaigns import permission_missing
from clipforge.channel_rows import WatchedVideoRow
from clipforge.db import ProjectRow
from clipforge.models import (
    AUTOPILOT_FAILURES_TO_STOP,
    AutopilotSettings,
    AutopilotStatus,
    AutopilotStop,
    AutopilotStopReason,
    Campaign,
)
from clipforge.watch.times import as_utc, utc_now

logger = logging.getLogger(__name__)
CAMPAIGNS_LINK = "/campaigns"
# The drafts that count against the daily quota: those that may be posted.
QUOTA_STATUSES = ("pending", "approved")
WAITING_STATUSES = ("pending", "needs_fix")


def paused_at(engine: Engine) -> datetime | None:
    """When the owner paused every autopilot; None if it is not paused."""
    with Session(engine) as session:
        row = session.get(AutopilotPauseRow, 1)
        return None if row is None else as_utc(row.paused_at)


def set_paused(
    engine: Engine, paused: bool, now: datetime | None = None
) -> datetime | None:
    """Pause (at now, default: the current time; an earlier pause keeps its
    time) or resume every campaign's autopilot; return paused_at."""
    with Session(engine) as session:
        row = session.get(AutopilotPauseRow, 1)
        if paused and row is None:
            session.add(AutopilotPauseRow(paused_at=utc_now() if now is None else now))
        elif not paused and row is not None:
            session.delete(row)
        session.commit()
    logger.info("autopilot: every campaign %s", "paused" if paused else "resumed")
    return paused_at(engine)


def drafts_today(engine: Engine, campaign_id: int, today: date) -> int:
    """How many drafts that may be posted (pending or approved) the autopilot
    made for the campaign on day today (the owner's local date)."""
    since = datetime.combine(today - timedelta(days=1), time.min, tzinfo=UTC)
    with Session(engine) as session:
        made = session.exec(
            select(DraftRow.created_at).where(
                col(DraftRow.campaign_id) == campaign_id,
                col(DraftRow.status).in_(QUOTA_STATUSES),
                col(DraftRow.created_at) >= since,
            )
        ).all()
    return sum(as_utc(at).astimezone().date() == today for at in made)


def quota_left(engine: Engine, autopilot: AutopilotSettings, now: datetime) -> int:
    """How many more drafts that may be posted the campaign's autopilot may
    make on now's local date: max_posts_per_day (each approved draft is
    posted once on each of the campaign's accounts) less those made."""
    made = drafts_today(engine, autopilot.campaign_id, now.astimezone().date())
    return max(autopilot.max_posts_per_day - made, 0)


def stop_reason(
    engine: Engine,
    campaign: Campaign,
    autopilot: AutopilotSettings,
    now: datetime,
    *,
    quota: bool = True,
) -> AutopilotStop | None:
    """Why the campaign's autopilot (on) makes no drafts at now; None if it
    may. With quota False the daily quota is not looked at (a new upload is
    still made the autopilot's way: its drafts come once the quota allows)."""
    reason, detail = _campaign_stop(campaign, now.astimezone().date())
    if paused_at(engine) is not None:
        reason, detail = "paused", "every autopilot is paused: resume it"
    elif reason is None and quota and quota_left(engine, autopilot, now) == 0:
        reason = "daily_quota"
        detail = (
            f"today's {autopilot.max_posts_per_day} drafts are made: more come tomorrow"
        )
    if reason is None:
        return None
    return AutopilotStop(campaign_id=campaign.id, reason=reason, detail=detail)


def check(
    engine: Engine,
    campaign: Campaign,
    autopilot: AutopilotSettings,
    now: datetime,
    *,
    quota: bool = True,
) -> AutopilotStop | None:
    """stop_reason, and alert the owner of an automatic stop (once a day per
    campaign and reason; the owner's pause makes no alert)."""
    stop = stop_reason(engine, campaign, autopilot, now, quota=quota)
    if stop is not None and stop.reason != "paused":
        logger.warning("autopilot of campaign %d stopped: %s", campaign.id, stop.detail)
        day = now.astimezone().date().isoformat()
        notifications.notify(
            engine,
            "autopilot_stopped",
            f"Autopilot of {campaign.name} stopped",
            f"No drafts are made: {stop.detail}.",
            CAMPAIGNS_LINK,
            dedupe_key=f"autopilot:{campaign.id}:{stop.reason}:{day}",
        )
    return stop


def status(engine: Engine, now: datetime | None = None) -> AutopilotStatus:
    """Whether every autopilot is paused, and why each campaign's autopilot
    that is on is stopped at now (default: the current time)."""
    now = utc_now() if now is None else now
    with Session(engine) as session:
        rows = session.exec(
            select(AutopilotSettingsRow, CampaignRow)
            .join(CampaignRow, col(CampaignRow.id) == AutopilotSettingsRow.campaign_id)
            .where(col(AutopilotSettingsRow.enabled))
            .order_by(col(CampaignRow.id))
        ).all()
        campaigns = [(c.to_model(), s.campaign_id) for s, c in rows]
    stops = [
        stop
        for campaign, campaign_id in campaigns
        if (
            stop := stop_reason(
                engine, campaign, get_settings(engine, campaign_id), now
            )
        )
        is not None
    ]
    since = paused_at(engine)
    return AutopilotStatus(paused=since is not None, paused_at=since, stops=stops)


def expire_drafts(engine: Engine, now: datetime | None = None) -> list[int]:
    """Expire every waiting draft (pending or needs_fix) made draft_ttl_days
    of its campaign or more before now (default: the current time); return
    their ids in order."""
    now = utc_now() if now is None else now
    ttl: dict[int, int] = {}
    with Session(engine) as session:
        waiting = session.exec(
            select(DraftRow)
            .where(col(DraftRow.status).in_(WAITING_STATUSES))
            .order_by(col(DraftRow.id))
        ).all()
        expired: list[int] = []
        for draft in waiting:
            if draft.campaign_id not in ttl:
                settings = session.get(AutopilotSettingsRow, draft.campaign_id)
                ttl[draft.campaign_id] = (
                    AutopilotSettings(campaign_id=draft.campaign_id).draft_ttl_days
                    if settings is None
                    else settings.draft_ttl_days
                )
            if as_utc(draft.created_at) + timedelta(days=ttl[draft.campaign_id]) <= now:
                assert draft.id is not None
                expired.append(draft.id)
        if expired:
            session.exec(
                update(DraftRow)
                .where(col(DraftRow.id).in_(expired))
                .values(status="expired")
            )
            session.commit()
    if expired:
        logger.info("autopilot: drafts %s expired", expired)
    return expired


def after_failed_job(engine: Engine, project_id: int) -> bool:
    """Once the process job of project project_id failed: if the project is
    an upload that Auto Import made for a campaign whose autopilot is on, and
    the campaign's last AUTOPILOT_FAILURES_TO_STOP finished uploads all
    failed, turn its autopilot off and alert the owner; whether it did. A
    failure here is logged, never raised."""
    try:
        return _stop_after_failures(engine, project_id)
    except Exception:
        logger.exception("autopilot: could not check the failures of %d", project_id)
        return False


def _stop_after_failures(engine: Engine, project_id: int) -> bool:
    with Session(engine) as session:
        project = session.get(ProjectRow, project_id)
        campaign_id = None if project is None else project.campaign_id
        settings = (
            None
            if campaign_id is None
            else session.get(AutopilotSettingsRow, campaign_id)
        )
        if campaign_id is None or settings is None or not settings.enabled:
            return False
        last = session.exec(
            select(ProjectRow.status)
            .join(WatchedVideoRow, col(WatchedVideoRow.project_id) == ProjectRow.id)
            .where(
                col(ProjectRow.campaign_id) == campaign_id,
                col(ProjectRow.status).in_(("done", "failed")),
            )
            .order_by(col(ProjectRow.id).desc())
            .limit(AUTOPILOT_FAILURES_TO_STOP)
        ).all()
        if len(last) < AUTOPILOT_FAILURES_TO_STOP or any(s != "failed" for s in last):
            return False
        settings.enabled = False
        session.add(settings)
        campaign_row = session.get(CampaignRow, campaign_id)
        name = "" if campaign_row is None else campaign_row.name
        session.commit()
    logger.warning(
        "autopilot of campaign %d turned off: %d uploads in a row failed",
        campaign_id,
        AUTOPILOT_FAILURES_TO_STOP,
    )
    notifications.notify(
        engine,
        "autopilot_stopped",
        f"Autopilot of {name} turned off",
        f"The last {AUTOPILOT_FAILURES_TO_STOP} uploads of the campaign failed "
        "to process. See the projects, then turn the autopilot on again.",
        CAMPAIGNS_LINK,
        dedupe_key=f"autopilot:{campaign_id}:failures:{project_id}",
    )
    return True


def _campaign_stop(
    campaign: Campaign, today: date
) -> tuple[AutopilotStopReason | None, str]:
    """Whether the campaign itself stops its autopilot on day today: missing
    permission evidence, a paused or ended campaign, a passed end date."""
    missing = permission_missing(campaign)
    if missing:
        return "permission_missing", f"add {', '.join(missing)}"
    if campaign.status != "active":
        return "campaign_inactive", f"the campaign is {campaign.status}"
    if campaign.end_date is not None and today > campaign.end_date:
        return "campaign_ended", f"the campaign ended on {campaign.end_date}"
    return None, ""
