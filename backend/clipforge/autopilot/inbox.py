"""The Approval Inbox of the autopilot (SPEC-v2 3.19): the drafts waiting for
the owner, their review notes and the owner's decisions.

Anyone may list the drafts, make a draft of a campaign clip (create_draft)
and add a review note (add_note): the owner in the app, or an agent through
an API key or the MCP server. Approving and rejecting are the owner's alone;
the API enforces it (api.drafts, 403 human_only), this module only does what
it is asked. Approving queues the clip's posts (approval_plan says where and
when) and records the decision (mark_approved); rejecting records it with
the owner's reason (reject). Each decision is a FeedbackEvent that the
campaign's curate prompt and scores learn from.

Drafts that waited longer than their campaign's draft_ttl_days expire
before they are listed or decided (safety.expire_drafts).
"""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge import campaign_accounts, campaigns, social_accounts
from clipforge.autopilot import safety
from clipforge.autopilot.rows import DraftRow, FeedbackEventRow
from clipforge.autopilot.settings import get_settings
from clipforge.campaign_rules import check_clip
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import (
    DRAFT_NOTES_MAX,
    BulkSchedule,
    Draft,
    DraftApprove,
    DraftNote,
    DraftNoteAuthor,
    DraftStatus,
    FeedbackAction,
    PostTarget,
    RejectReason,
    ScheduleRules,
)
from clipforge.watch.times import utc_now


class DraftNotFound(LookupError):
    """There is no draft with this id."""


class ClipNotFound(LookupError):
    """There is no clip with this id."""


class NotInCampaign(ValueError):
    """The clip's project belongs to no campaign, so it cannot be a draft."""


class DraftExists(Exception):
    """The clip already has a draft (a clip has at most one)."""


class DraftDecided(Exception):
    """The draft no longer waits (approved, rejected or expired)."""


class TooManyNotes(Exception):
    """The draft already has DRAFT_NOTES_MAX review notes."""


class NoSlots(ValueError):
    """Neither the owner nor the campaign's autopilot gave posting slots."""


def list_drafts(
    engine: Engine,
    status: DraftStatus | None = None,
    campaign_id: int | None = None,
    now: datetime | None = None,
) -> list[Draft]:
    """Return the drafts, newest first, of status and campaign_id if given,
    after expiring the old ones at now (default: the current time)."""
    safety.expire_drafts(engine, now)
    query = select(DraftRow).order_by(
        col(DraftRow.created_at).desc(), col(DraftRow.id).desc()
    )
    if status is not None:
        query = query.where(col(DraftRow.status) == status)
    if campaign_id is not None:
        query = query.where(col(DraftRow.campaign_id) == campaign_id)
    with Session(engine) as session:
        return [row.to_model() for row in session.exec(query).all()]


def get_draft(engine: Engine, draft_id: int) -> Draft:
    """Return draft draft_id; DraftNotFound if there is none."""
    with Session(engine) as session:
        return _row(session, draft_id).to_model()


def waiting_draft(engine: Engine, draft_id: int, now: datetime | None = None) -> Draft:
    """Return draft draft_id if it still waits for the owner (pending or
    needs_fix, after expiring the old drafts at now); DraftNotFound,
    DraftDecided otherwise."""
    safety.expire_drafts(engine, now)
    draft = get_draft(engine, draft_id)
    if draft.status not in safety.WAITING_STATUSES:
        raise DraftDecided(f"draft {draft_id} is {draft.status}, it no longer waits")
    return draft


def create_draft(engine: Engine, clip_id: int, now: datetime | None = None) -> Draft:
    """Make a draft of clip clip_id at now (default: the current time) for
    the campaign of its project: pending if the clip passes the campaign's
    rules on the owner's local date, else needs_fix (with the rule results).
    ClipNotFound, NotInCampaign (no campaign), DraftExists (one already)."""
    now = utc_now() if now is None else now
    with Session(engine) as session:
        clip_row = session.get(ClipRow, clip_id)
        if clip_row is None:
            raise ClipNotFound(f"clip {clip_id} does not exist")
        project_row = session.get(ProjectRow, clip_row.project_id)
        assert project_row is not None
        clip, project = clip_row.to_model(), project_row.to_model()
        taken = session.exec(
            select(DraftRow.id).where(col(DraftRow.clip_id) == clip_id)
        ).first()
    if taken is not None:
        raise DraftExists(f"clip {clip_id} already has draft {taken}")
    if project.campaign_id is None:
        raise NotInCampaign(f"clip {clip_id} is not in a campaign's project")
    campaign = campaigns.get_campaign(engine, project.campaign_id)
    check = check_clip(clip, project, campaign, now.astimezone().date())
    row = DraftRow(
        clip_id=clip_id,
        campaign_id=campaign.id,
        status="pending" if check.passed else "needs_fix",
        rule_results=check.results,
        created_at=now,
    )
    with Session(engine) as session:
        session.add(row)
        session.commit()
        return row.to_model()


def add_note(
    engine: Engine,
    draft_id: int,
    text: str,
    by: DraftNoteAuthor,
    now: datetime | None = None,
) -> Draft:
    """Add a review note by the owner or an agent to draft draft_id (in any
    status) at now (default: the current time); return the draft.
    DraftNotFound, TooManyNotes."""
    note = DraftNote(text=text, by=by, at=utc_now() if now is None else now)
    with Session(engine) as session:
        row = _row(session, draft_id)
        if len(row.notes) >= DRAFT_NOTES_MAX:
            raise TooManyNotes(f"draft {draft_id} has {DRAFT_NOTES_MAX} notes")
        row.notes = [*row.notes, note]
        session.add(row)
        session.commit()
        return row.to_model()


def reject(
    engine: Engine,
    draft_id: int,
    reason: RejectReason | None,
    now: datetime | None = None,
) -> Draft:
    """Reject draft draft_id (the owner's decision) for reason at now
    (default: the current time) and record the feedback; return the draft.
    DraftNotFound, DraftDecided."""
    now = utc_now() if now is None else now
    waiting_draft(engine, draft_id, now)
    with Session(engine) as session:
        row = _row(session, draft_id)
        row.status, row.reject_reason, row.decided_at = "rejected", reason, now
        session.add(row)
        session.add(_feedback(row, now, reason))
        session.commit()
        return row.to_model()


def pending_drafts(
    engine: Engine, campaign_id: int, now: datetime | None = None
) -> list[Draft]:
    """The campaign's pending drafts (they pass its rules), oldest first,
    after expiring the old ones at now (default: the current time)."""
    drafts = list_drafts(engine, "pending", campaign_id, now)
    return sorted(drafts, key=lambda d: (d.created_at, d.id))


def approval_plan(
    engine: Engine, campaign_id: int, clip_ids: list[int], body: DraftApprove
) -> BulkSchedule:
    """Return how to queue the posts of the clips of campaign campaign_id's
    drafts: every clip to each of the autopilot's accounts (none: the
    campaign's accounts) saying body.text, in the next free slot of
    body.rules (None: the autopilot's slots), at most the autopilot's
    max_posts_per_day a day. NoSlots without rules;
    campaign_accounts.NoCampaignAccounts without accounts and
    PlatformNotAllowed for an account of a platform the campaign forbids."""
    campaign = campaigns.get_campaign(engine, campaign_id)
    autopilot = get_settings(engine, campaign_id)
    rules = body.rules if body.rules is not None else autopilot.slots
    if rules is None:
        raise NoSlots("give the posting slots, or set them in the campaign's autopilot")
    if not autopilot.account_ids:
        targets = campaign_accounts.bulk_targets(engine, campaign, body.text)
    else:
        for account_id in autopilot.account_ids:
            account = social_accounts.get_account(engine, account_id)
            campaign_accounts.check_platform(campaign, account)
        targets = [
            PostTarget(account_id=account_id, text=body.text)
            for account_id in autopilot.account_ids
        ]
    return BulkSchedule(
        clip_ids=clip_ids,
        targets=targets,
        rules=_capped(rules, autopilot.max_posts_per_day),
        queue=True,
    )


def mark_approved(
    engine: Engine, draft_ids: Iterable[int], now: datetime | None = None
) -> list[Draft]:
    """Mark the drafts approved (the owner's decision, their posts queued)
    at now (default: the current time) and record the feedback; return
    them in order."""
    now = utc_now() if now is None else now
    ids = list(draft_ids)
    with Session(engine) as session:
        for draft_id in ids:
            row = _row(session, draft_id)
            row.status, row.reject_reason, row.decided_at = "approved", None, now
            session.add(row)
            session.add(_feedback(row, now, None))
        session.commit()
        return [_row(session, draft_id).to_model() for draft_id in ids]


def _capped(rules: ScheduleRules, per_day: int) -> ScheduleRules:
    """rules with at most per_day posts a day on one account."""
    daily = min(len(rules.daily_times()), per_day)
    return rules.model_copy(update={"posts_per_day": daily})


def _feedback(
    row: DraftRow, now: datetime, reason: RejectReason | None
) -> FeedbackEventRow:
    """The feedback event of the owner's decision about the draft's clip."""
    action: FeedbackAction = "approved" if row.status == "approved" else "rejected"
    return FeedbackEventRow(
        clip_id=row.clip_id,
        campaign_id=row.campaign_id,
        action=action,
        reason=reason,
        at=now,
    )


def _row(session: Session, draft_id: int) -> DraftRow:
    """Return draft draft_id's row; DraftNotFound if there is none."""
    row = session.get(DraftRow, draft_id)
    if row is None:
        raise DraftNotFound(f"draft {draft_id} does not exist")
    return row
