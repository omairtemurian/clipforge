"""Submission tracker endpoints (SPEC-v2 3.18): the owner's record of the
published posts of a campaign submitted on its board.

    GET   /submissions        ?campaign_id=&status= -> [SubmissionView]
    GET   /submissions/{id}   -> SubmissionView
    PATCH /submissions/{id}   SubmissionPatch -> SubmissionView

Each view has copy_text, the post URL with the campaign's required
information. 409 illegal_submission_move for a status that cannot follow
the current one (clipforge.submissions.TRANSITIONS).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from clipforge import submissions
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError, not_found
from clipforge.models import SubmissionPatch, SubmissionStatus, SubmissionView

router = APIRouter(prefix="/submissions")

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("")
def list_submissions(
    engine: EngineDep,
    campaign_id: int | None = None,
    status: SubmissionStatus | None = None,
) -> list[SubmissionView]:
    """Return the submissions of the published posts of campaign projects,
    newest first; campaign_id and status narrow them."""
    return submissions.list_submissions(engine, campaign_id, status)


@router.get("/{submission_id}")
def get_submission(submission_id: int, engine: EngineDep) -> SubmissionView:
    """Return one submission."""
    try:
        return submissions.get_submission(engine, submission_id)
    except submissions.SubmissionNotFound as exc:
        raise not_found("submission", submission_id) from exc


@router.patch("/{submission_id}")
def patch_submission(
    submission_id: int, body: SubmissionPatch, engine: EngineDep
) -> SubmissionView:
    """Tick a post as submitted (or untick it), record the board's answer
    (approved, rejected, paid) and the approved views, payout and notes."""
    try:
        return submissions.update_submission(engine, submission_id, body)
    except submissions.SubmissionNotFound as exc:
        raise not_found("submission", submission_id) from exc
    except submissions.IllegalSubmissionMove as exc:
        raise ApiError(409, "illegal_submission_move", str(exc)) from exc
