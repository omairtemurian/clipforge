"""The style-match of a rendered clip (a Pro Edit variant) against a style
recipe (SPEC-v3 4.4): its video is measured with the same extractors as a
reference (style/store.measure_features) and scored by recipe.style_match.

Measuring takes a while, so the last match of a clip is kept as JSON in
its project's work directory (style_match_<clip id>.json) with the time
the video was last written; it no longer counts once the video changes.
"""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.db import ClipRow
from clipforge.job_rows import process_work_dir
from clipforge.models import StyleMatch
from clipforge.pipeline.step import StepError
from clipforge.proedit.plan_store import current_plan
from clipforge.proedit.rows import StyleRecipeRow
from clipforge.proedit.style.metrics import metric_values
from clipforge.proedit.style.recipe import style_match, targets_of
from clipforge.proedit.style.store import Analyzer, measure_features


class StyleMatchError(Exception):
    """The clip cannot be scored: missing (404) or not ready (409)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class _Cached(BaseModel):
    video_mtime: float
    match: StyleMatch


def _cache_path(session: Session, clip: ClipRow) -> Path:
    return process_work_dir(session, clip.project_id) / f"style_match_{clip.id}.json"


def _video(clip: ClipRow) -> Path:
    video = Path(clip.output_path) if clip.output_path else None
    if clip.status != "rendered" or video is None or not video.is_file():
        raise StyleMatchError(409, f"clip {clip.id} has no rendered video")
    return video


def _recipe(session: Session, clip_id: int, recipe_id: int | None) -> StyleRecipeRow:
    if recipe_id is None:
        plan = current_plan(session, clip_id)
        recipe_id = plan.style_recipe_id if plan else None
    if recipe_id is None:
        raise StyleMatchError(409, f"clip {clip_id} has no style recipe")
    recipe = session.get(StyleRecipeRow, recipe_id)
    if recipe is None:
        raise StyleMatchError(404, f"style recipe {recipe_id} not found")
    return recipe


def _clip(session: Session, clip_id: int) -> ClipRow:
    clip = session.get(ClipRow, clip_id)
    if clip is None:
        raise StyleMatchError(404, f"clip {clip_id} not found")
    return clip


def last_match(
    session: Session, clip_id: int, recipe_id: int | None = None
) -> StyleMatch | None:
    """Return the kept match of clip clip_id against recipe recipe_id
    (default: its plan's recipe), or None if there is none for its current
    video. Raises StyleMatchError if the clip, its recipe or its video is
    missing."""
    clip = _clip(session, clip_id)
    recipe = _recipe(session, clip_id, recipe_id)
    video = _video(clip)
    try:
        path = _cache_path(session, clip)
    except StepError as exc:
        raise StyleMatchError(409, str(exc)) from exc
    if not path.is_file():
        return None
    cached = _Cached.model_validate_json(path.read_text())
    if cached.video_mtime != video.stat().st_mtime or (
        cached.match.recipe_id != recipe.id
    ):
        return None
    return cached.match


def measure_match(
    engine: Engine,
    clip_id: int,
    recipe_id: int | None = None,
    analyzer: Analyzer | None = None,
) -> StyleMatch:
    """Measure clip clip_id's rendered video, score it against recipe
    recipe_id (default: its plan's recipe) with analyzer (default:
    store.measure_features), keep the match and return it. No database
    session is open while the video is measured. Raises StyleMatchError if
    the clip, its recipe or its video is missing or the video cannot be
    measured."""
    with Session(engine) as session:
        clip = _clip(session, clip_id)
        recipe = _recipe(session, clip_id, recipe_id).to_model()
        video = _video(clip)
        try:
            path = _cache_path(session, clip)
        except StepError as exc:
            raise StyleMatchError(409, str(exc)) from exc
    mtime = video.stat().st_mtime
    try:
        values = metric_values((analyzer or measure_features)(video))
    except StepError as exc:
        raise StyleMatchError(409, str(exc)) from exc
    result = style_match(values, targets_of(recipe))
    match = StyleMatch(
        clip_id=clip_id,
        recipe_id=recipe.id,
        recipe_name=recipe.name,
        score=result.score,
        metrics=result.metrics,
        measured_at=datetime.now(UTC),
    )
    path.write_text(_Cached(video_mtime=mtime, match=match).model_dump_json())
    return match
