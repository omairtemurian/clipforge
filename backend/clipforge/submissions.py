"""The submission tracker (SPEC-v2 3.18): after a post of a campaign's clip
is published, the owner copies its URL with the campaign's required
information, submits it on the campaign's board by hand (ClipForge never
automates a campaign board) and ticks it here; later the board's approved
views and the payout are entered.

A Submission is made for each published post (with a URL) of a project that
has a campaign, the first time the tracker lists it (sync).
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, col, select

from clipforge.campaign_rows import CampaignRow
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import (
    Campaign,
    SocialPlatform,
    SubmissionPatch,
    SubmissionStatus,
    SubmissionView,
)
from clipforge.social_rows import PostRow
from clipforge.submission_rows import SubmissionRow

# The legal moves: tick (submitted), untick, the board's answer, a payout, and
# a mistake or a resubmission after a rejection can be undone.
TRANSITIONS: dict[SubmissionStatus, frozenset[SubmissionStatus]] = {
    "not_submitted": frozenset({"submitted"}),
    "submitted": frozenset({"not_submitted", "approved", "rejected"}),
    "approved": frozenset({"submitted", "rejected", "paid"}),
    "rejected": frozenset({"submitted", "approved"}),
    "paid": frozenset({"approved"}),
}


# The statuses that the campaign board answers with.
ANSWERS: frozenset[SubmissionStatus] = frozenset({"approved", "rejected", "paid"})


class SubmissionNotFound(LookupError):
    """No submission has the id."""


class IllegalSubmissionMove(Exception):
    """A submission cannot go from old to new status."""

    def __init__(self, old: SubmissionStatus, new: SubmissionStatus) -> None:
        super().__init__(f"a {old} submission cannot become {new}")
        self.old = old
        self.new = new


def can_move(old: SubmissionStatus, new: SubmissionStatus) -> bool:
    """Return whether a submission may go from old to new (or stay)."""
    return old == new or new in TRANSITIONS[old]


def copy_text(campaign: Campaign | None, platform: SocialPlatform, url: str) -> str:
    """Return what the owner pastes into the campaign's board: the post URL
    first, then the campaign's required information (as far as it has
    some), one labeled line each."""
    lines = [url, ""]
    if campaign is not None:
        lines.append(f"Campaign: {campaign.name}")
    lines.append(f"Platform: {platform}")
    if campaign is not None:
        if campaign.required_credit_line:
            lines.append(f"Credit line: {campaign.required_credit_line}")
        if campaign.required_hashtags:
            tags = " ".join(f"#{tag}" for tag in campaign.required_hashtags)
            lines.append(f"Hashtags: {tags}")
        if campaign.required_tags_mentions:
            lines.append(f"Mentions: {' '.join(campaign.required_tags_mentions)}")
        if campaign.submission_instructions:
            lines.append(f"Instructions: {campaign.submission_instructions}")
    return "\n".join(lines)


def sync(engine: Engine) -> None:
    """Make a not_submitted submission for each published post with a URL of
    a campaign project that has none yet (safe to call at the same time from
    several requests)."""
    with Session(engine) as session:
        missing = session.exec(
            select(PostRow.id, ProjectRow.campaign_id)
            .join(ClipRow, col(ClipRow.id) == col(PostRow.clip_id))
            .join(ProjectRow, col(ProjectRow.id) == col(ClipRow.project_id))
            .outerjoin(SubmissionRow, col(SubmissionRow.post_id) == col(PostRow.id))
            .where(
                col(PostRow.status) == "published",
                col(PostRow.url).is_not(None),
                col(ProjectRow.campaign_id).is_not(None),
                col(SubmissionRow.id).is_(None),
            )
        ).all()
        for post_id, campaign_id in missing:
            session.execute(
                insert(SubmissionRow)
                .values(
                    post_id=post_id,
                    campaign_id=campaign_id,
                    status="not_submitted",
                    notes="",
                )
                .on_conflict_do_nothing(index_elements=["post_id"])
            )
        session.commit()


def list_submissions(
    engine: Engine,
    campaign_id: int | None = None,
    status: SubmissionStatus | None = None,
) -> list[SubmissionView]:
    """Return the submissions (of campaign campaign_id and with status, when
    given), newest post first, after making those of the published posts
    that have none."""
    sync(engine)
    with Session(engine) as session:
        query = _query()
        if campaign_id is not None:
            query = query.where(col(SubmissionRow.campaign_id) == campaign_id)
        if status is not None:
            query = query.where(col(SubmissionRow.status) == status)
        rows = session.exec(query.order_by(col(SubmissionRow.id).desc())).all()
        return _views(session, rows)


def get_submission(engine: Engine, submission_id: int) -> SubmissionView:
    """Return a submission; SubmissionNotFound if there is none."""
    with Session(engine) as session:
        rows = session.exec(
            _query().where(col(SubmissionRow.id) == submission_id)
        ).all()
        if not rows:
            raise SubmissionNotFound(f"submission {submission_id} not found")
        return _views(session, rows)[0]


def update_submission(
    engine: Engine, submission_id: int, patch: SubmissionPatch
) -> SubmissionView:
    """Change the fields of a submission that patch sends and return it.

    A new status must be a legal move (IllegalSubmissionMove otherwise,
    nothing changes); ticking "submitted" sets submitted_at to now and
    unticking clears it. The board's answer (approved, rejected, paid) or a
    change of the approved views or payout sets answered_at to now, going
    back to not_submitted or submitted clears it. SubmissionNotFound if there
    is none.
    """
    with Session(engine) as session:
        row = session.get(SubmissionRow, submission_id)
        if row is None:
            raise SubmissionNotFound(f"submission {submission_id} not found")
        changes = patch.model_dump(include=patch.model_fields_set)
        new = changes.pop("status", None)
        if new is not None and not can_move(row.status, new):
            raise IllegalSubmissionMove(row.status, new)
        if new is not None and new != row.status:
            if new == "submitted":
                row.submitted_at = datetime.now(UTC)
            elif new == "not_submitted":
                row.submitted_at = None
            row.status = new
            if new in ANSWERS:
                row.answered_at = datetime.now(UTC)
            else:
                row.answered_at = None
        for name, value in changes.items():
            if getattr(row, name) != value and name in ("approved_views", "payout_usd"):
                row.answered_at = datetime.now(UTC)
            setattr(row, name, value)
        session.add(row)
        session.commit()
    return get_submission(engine, submission_id)


def _query() -> Any:
    """Return the select of a submission with its post and its clip's title."""
    return (
        select(SubmissionRow, PostRow, ClipRow.title)
        .join(PostRow, col(PostRow.id) == col(SubmissionRow.post_id))
        .join(ClipRow, col(ClipRow.id) == col(PostRow.clip_id))
    )


def _views(session: Session, rows: Sequence[Any]) -> list[SubmissionView]:
    """Return the views of the (submission, post, clip title) rows."""
    ids = {sub.campaign_id for sub, _, _ in rows if sub.campaign_id is not None}
    by_id = {
        campaign.id: campaign.to_model()
        for campaign in session.exec(
            select(CampaignRow).where(col(CampaignRow.id).in_(ids))
        )
        if campaign.id is not None
    }
    return [
        _view(sub, post, title, by_id.get(sub.campaign_id)) for sub, post, title in rows
    ]


def _view(
    sub: SubmissionRow, post: PostRow, title: str, campaign: Campaign | None
) -> SubmissionView:
    """Return the view of one submission."""
    url = post.url or ""
    return SubmissionView(
        **sub.to_model().model_dump(),
        platform=post.platform,
        post_url=url,
        clip_id=post.clip_id,
        clip_title=title,
        campaign_name=None if campaign is None else campaign.name,
        copy_text=copy_text(campaign, post.platform, url),
    )
