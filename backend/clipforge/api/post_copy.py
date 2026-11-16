"""The post text generator endpoint (SPEC-v2 3.10): the title, description
and hashtags of a clip's post on one platform, written by the LLM.

    POST /clips/{id}/post-copy   PostCopyRequest -> PostCopy

Nothing is saved: the Schedule post form puts the answer in its fields.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import social_accounts, usage
from clipforge.api.deps import clip_row, get_engine, get_llm, project_row, work_dir
from clipforge.api.errors import ApiError, not_found
from clipforge.llm import LLMClient
from clipforge.llm_http import LLMError
from clipforge.models import PostCopy, PostCopyRequest
from clipforge.pipeline.step import StepError
from clipforge.post_copy import PostCopyError, write_copy
from clipforge.post_tags import required_hashtags

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/clips/{clip_id}/post-copy")
def post_copy(
    clip_id: int,
    body: PostCopyRequest,
    engine: Annotated[Engine, Depends(get_engine)],
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> PostCopy:
    """Write the clip's post on body.platform from its words, hook and the
    project's credit line (post_copy.write_copy): all of it new, or what
    the options of the rewrite change. The always-included hashtags (the
    setting, the account's, the campaign's) are in every answer. Answers
    404 for an unknown account, 502 if the LLM cannot be reached or sends
    no valid text, and 409 if the clip's transcript is missing."""
    account = None
    if body.account_id is not None:
        try:
            account = social_accounts.get_account(engine, body.account_id)
        except social_accounts.AccountNotFound as exc:
            raise not_found("account", body.account_id) from exc
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        credit = project_row(session, clip.project_id).credit_line
        work = work_dir(session, clip.project_id)
    try:
        with usage.recording(engine, clip.project_id):
            required = required_hashtags(engine, clip.project_id, account)
            return write_copy(llm, body, clip, work, credit, required)
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    except (LLMError, PostCopyError) as exc:
        logger.warning("clip %d: no post copy: %s", clip_id, exc)
        raise ApiError(502, "llm_error", str(exc)) from exc
