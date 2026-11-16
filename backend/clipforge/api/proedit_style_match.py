"""Pro Edit style-match endpoints (SPEC-v3 4.4), under /proedit: how close
a rendered clip (a Pro Edit variant) is to a style recipe, 0-100. Measuring
reads the whole video like a reference's analysis, so the last match is
kept until the video changes. The flag proedit.enabled turns them off like
the other Pro Edit endpoints.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError
from clipforge.api.proedit import require_proedit
from clipforge.models import StyleMatch
from clipforge.proedit.style import match
from clipforge.proedit.style.match import StyleMatchError

router = APIRouter(prefix="/proedit", dependencies=[Depends(require_proedit)])

EngineDep = Annotated[Engine, Depends(get_engine)]


def _api_error(error: StyleMatchError) -> ApiError:
    code = "not_found" if error.status == 404 else "conflict"
    return ApiError(error.status, code, str(error))


@router.get("/clips/{clip_id}/style-match")
def get_style_match(
    clip_id: int, engine: EngineDep, recipe_id: int | None = None
) -> StyleMatch | None:
    """Return the kept match of clip clip_id's video against recipe
    recipe_id (default: the recipe of its plan), or null if it was not
    measured since the video last changed. 404 if the clip or recipe does
    not exist; 409 if the clip has no recipe or no rendered video."""
    with Session(engine) as session:
        try:
            return match.last_match(session, clip_id, recipe_id)
        except StyleMatchError as error:
            raise _api_error(error) from error


@router.post("/clips/{clip_id}/style-match")
def measure_style_match(
    clip_id: int, engine: EngineDep, recipe_id: int | None = None
) -> StyleMatch:
    """Measure clip clip_id's rendered video and score it against recipe
    recipe_id (default: the recipe of its plan); answers when done. 404 if
    the clip or recipe does not exist; 409 if the clip has no recipe or no
    rendered video, or the video cannot be read."""
    try:
        return match.measure_match(engine, clip_id, recipe_id)
    except StyleMatchError as error:
        raise _api_error(error) from error
