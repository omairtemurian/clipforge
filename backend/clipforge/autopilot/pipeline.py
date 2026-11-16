"""The draft pipeline of the autopilot (SPEC-v2 3.19).

A new upload of a campaign's watched channel (Auto Import, 3.1) becomes a
project with the campaign's preset; with the campaign's autopilot on, the
project is also made the autopilot's way (import_settings: its clip length
range, caption and brand template, and only as many clips as may become
drafts). When the project's process job is done (make_drafts), its best
rendered clips, up to max_clips_per_source, go through the campaign rule
checker (campaign_rules): a clip that passes becomes a pending Draft for the
Approval Inbox, one that fails a needs_fix Draft with the rule results. With
the autopilot's Pro Edit switch on and the campaign's allow_heavy_edits "true",
each pending draft's clip also gets a Pro Edit variant (autopilot.proedit).

The autopilot stops there: it never posts, schedules or submits anything.
Approving a draft is the owner's act. While a safety switch stops it
(autopilot.safety: the global pause, missing permission, a paused or ended
campaign, the daily quota), new uploads are imported as plain campaign
projects and no drafts are made.
"""

import logging
from datetime import datetime

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge.autopilot import proedit, safety
from clipforge.autopilot.rows import DraftRow
from clipforge.autopilot.settings import get_settings
from clipforge.campaign_rows import CampaignRow
from clipforge.campaign_rules import check_clip
from clipforge.captions_templates import load_templates
from clipforge.channel_rows import WatchedVideoRow
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import (
    CUSTOM_LENGTH_MAX_S,
    AutopilotSettings,
    Campaign,
    Clip,
    Draft,
    ProcessingSettings,
)
from clipforge.watch.times import utc_now

logger = logging.getLogger(__name__)


def import_settings(
    engine: Engine, campaign: Campaign, settings: ProcessingSettings
) -> ProcessingSettings:
    """Return settings (already with the campaign's preset) for a new upload
    of the campaign's watched channel: unchanged while its autopilot is off
    or stopped (safety.check, the daily quota aside), else made the
    autopilot's way (autopilot_processing)."""
    autopilot = get_settings(engine, campaign.id)
    if not autopilot.enabled:
        return settings
    if safety.check(engine, campaign, autopilot, utc_now(), quota=False):
        return settings
    return autopilot_processing(settings, autopilot, campaign)


def autopilot_processing(
    settings: ProcessingSettings, autopilot: AutopilotSettings, campaign: Campaign
) -> ProcessingSettings:
    """Return settings with what the autopilot asks for: max_clips_per_source
    clips, its caption and brand templates (each only if set and still
    there) and, if it sets a bound, the "custom" length range of its bounds
    (a missing one is the campaign's)."""
    changes: dict[str, object] = {"num_clips": autopilot.max_clips_per_source}
    template = autopilot.caption_template
    if template is not None and template in load_templates():
        changes["caption_template"] = template
    if autopilot.brand_template_id is not None:
        changes["brand_template_id"] = autopilot.brand_template_id
    length = _length_range(autopilot, campaign)
    if length is not None:
        changes["length_presets"] = ["custom"]
        changes["custom_length_min_s"], changes["custom_length_max_s"] = length
    return ProcessingSettings.model_validate(settings.model_dump() | changes)


def make_drafts(
    engine: Engine, project_id: int, now: datetime | None = None
) -> list[Draft]:
    """Make the drafts of project project_id, whose process job is done, at
    now (default: the current time); return the new drafts, best clip first.

    Only a project that Auto Import made for a campaign whose autopilot is
    on and not stopped (safety.check) gets drafts. Its rendered clips of the
    current result set, best overall score first, that have no draft yet
    become drafts, until the project has max_clips_per_source of them:
    pending if the clip passes the campaign rules on the owner's local date,
    else needs_fix. A pending draft over the day's quota (safety.quota_left)
    ends it. rule_results keeps every result (the failed ones have passed
    False).
    """
    now = utc_now() if now is None else now
    found = _autopilot_project(engine, project_id)
    if found is None:
        return []
    campaign, autopilot = found
    if safety.check(engine, campaign, autopilot, now) is not None:
        return []
    left = safety.quota_left(engine, autopilot, now)
    today = now.astimezone().date()
    with Session(engine) as session:
        project_row = session.get(ProjectRow, project_id)
        assert project_row is not None
        project = project_row.to_model()
        clip_rows = session.exec(
            select(ClipRow).where(
                col(ClipRow.project_id) == project_id,
                col(ClipRow.result_set) == project.result_set,
            )
        ).all()
        clips = [row.to_model() for row in clip_rows]
        drafted = set(
            session.exec(
                select(DraftRow.clip_id).where(
                    col(DraftRow.clip_id).in_([clip.id for clip in clips])
                )
            )
        )
        room = autopilot.max_clips_per_source - len(drafted)
        new: list[DraftRow] = []
        for clip in _best_rendered(clips, drafted)[: max(room, 0)]:
            check = check_clip(clip, project, campaign, today)
            if check.passed:
                if left == 0:
                    break
                left -= 1
            new.append(
                DraftRow(
                    clip_id=clip.id,
                    campaign_id=campaign.id,
                    status="pending" if check.passed else "needs_fix",
                    rule_results=check.results,
                    created_at=now,
                )
            )
        session.add_all(new)
        session.commit()
        drafts = [row.to_model() for row in new]
    if drafts:
        logger.info(
            "autopilot: project %d has %d new drafts (%d need a fix)",
            project_id,
            len(drafts),
            sum(d.status == "needs_fix" for d in drafts),
        )
        proedit.start_variants(
            engine,
            campaign,
            autopilot,
            [d.clip_id for d in drafts if d.status == "pending"],
        )
    return drafts


def drafts_after_job(engine: Engine, project_id: int) -> None:
    """Make the drafts of project project_id (make_drafts) once its process
    job is done; a failure is logged, never raised, so the job stays done."""
    try:
        make_drafts(engine, project_id)
    except Exception:
        logger.exception("autopilot: no drafts for project %d", project_id)


def _autopilot_project(
    engine: Engine, project_id: int
) -> tuple[Campaign, AutopilotSettings] | None:
    """Return the campaign of project project_id and its autopilot settings
    if Auto Import made the project for the campaign and its autopilot is
    on, else None."""
    with Session(engine) as session:
        project = session.get(ProjectRow, project_id)
        if project is None or project.campaign_id is None:
            return None
        imported = session.exec(
            select(WatchedVideoRow.video_id).where(
                col(WatchedVideoRow.project_id) == project_id
            )
        ).first()
        campaign_row = session.get(CampaignRow, project.campaign_id)
        if imported is None or campaign_row is None:
            return None
        campaign = campaign_row.to_model()
    autopilot = get_settings(engine, campaign.id)
    return (campaign, autopilot) if autopilot.enabled else None


def _best_rendered(clips: list[Clip], drafted: set[int]) -> list[Clip]:
    """The rendered clips that have no draft, best overall score first (the
    older clip first on a tie)."""
    ready = [c for c in clips if c.status == "rendered" and c.id not in drafted]
    return sorted(ready, key=lambda c: (-c.scores.overall, c.id))


def _length_range(
    autopilot: AutopilotSettings, campaign: Campaign
) -> tuple[float, float] | None:
    """The (min, max) clip length of the autopilot's projects; None if the
    autopilot sets no bound or the bounds leave no custom range (the
    campaign's length presets stay then)."""
    if autopilot.min_clip_s is None and autopilot.max_clip_s is None:
        return None
    low = autopilot.min_clip_s
    high = autopilot.max_clip_s
    low = campaign.min_duration_s if low is None else low
    high = campaign.max_duration_s if high is None else high
    low = 0.0 if low is None else low
    high = CUSTOM_LENGTH_MAX_S if high is None else min(high, CUSTOM_LENGTH_MAX_S)
    if low >= high:
        logger.warning(
            "autopilot of campaign %d: no clip length fits %g-%g s; "
            "keeping the campaign's lengths",
            campaign.id,
            low,
            high,
        )
        return None
    return low, high
