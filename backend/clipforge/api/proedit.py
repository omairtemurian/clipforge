"""Pro Edit endpoints (SPEC-v3 3.8), under /proedit.

Every endpoint of this router first checks the feature flag
proedit.enabled (proedit/config.py): when it is off they all answer 404
{error: "proedit_disabled"}, so the app hides its Pro Edit entry.

A start makes a new variant clip of an original and queues its "proedit"
job (proedit/runs.py, proedit/run_job.py); the original is never changed.
On a variant: its runs and plans, the editor's patch and reset (new plan
versions, no render), and the jobs that regenerate the plan, run the
critic again or render the current plan. Agents (API keys, MCP) may do all
of it: a variant is a draft, and approving or publishing it stays
human-only like every clip's.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import assets, config
from clipforge.api.deps import (
    clip_row,
    get_engine,
    require_usage_budget,
    wake_worker,
    work_dir,
)
from clipforge.api.errors import ApiError, not_found
from clipforge.api.music import music_track
from clipforge.models import (
    Clip,
    ProEditChoices,
    ProEditEstimate,
    ProEditItemsUpdate,
    ProEditOptions,
    ProEditPlan,
    ProEditRun,
    ProEditRunMode,
    ProEditStarted,
    ProEditStatus,
)
from clipforge.pipeline.step import StepError
from clipforge.proedit.choices import clip_choices
from clipforge.proedit.config import DISABLED_ERROR, DISABLED_MESSAGE
from clipforge.proedit.plan_store import current_plan, plan_versions
from clipforge.proedit.run_estimate import run_estimate
from clipforge.proedit.run_inputs import RunInputError
from clipforge.proedit.runs import (
    ProEditRunError,
    get_run,
    list_runs,
    patch_plan,
    queue_run,
    reset_plan,
    start_run,
)
from clipforge.proedit.variants import list_variants
from clipforge.storage import StorageRefused, require_not_archived

EngineDep = Annotated[Engine, Depends(get_engine)]


def require_proedit() -> None:
    """Raise the 404 proedit_disabled ApiError if Pro Edit is turned off."""
    if not config.settings.proedit.enabled:
        raise ApiError(404, DISABLED_ERROR, DISABLED_MESSAGE)


router = APIRouter(prefix="/proedit", dependencies=[Depends(require_proedit)])


@router.get("/status")
def get_proedit_status() -> ProEditStatus:
    """Return that Pro Edit is available and how many critic rounds a run
    makes at most (404 proedit_disabled when it is off)."""
    rounds = config.settings.proedit.critic_max_rounds
    return ProEditStatus(enabled=True, critic_max_rounds=rounds)


@router.get("/clips/{clip_id}/variants")
def get_proedit_variants(clip_id: int, engine: EngineDep) -> list[Clip]:
    """Return the Pro Edit variants of clip clip_id, oldest first; 404 if
    the clip does not exist."""
    with Session(engine) as session:
        clip_row(session, clip_id)
    return list_variants(engine, clip_id)


@router.get("/clips/{clip_id}/choices")
def get_proedit_choices(clip_id: int, engine: EngineDep) -> ProEditChoices:
    """Return what a Pro Edit of clip clip_id may choose: the presets, music
    beds and style recipes, its campaign's heavy-edit rule and the highest
    intensity (proedit/choices.py); 404 if the clip does not exist."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        found = assets.list_assets(session, kind="music")
    tracks = [track for asset in found if (track := music_track(asset)) is not None]
    return clip_choices(engine, clip, tracks)


@router.post("/clips/{clip_id}/runs", status_code=202)
def start_proedit(
    clip_id: int,
    request: Request,
    engine: EngineDep,
    options: ProEditOptions | None = None,
) -> ProEditStarted:
    """Make a Pro Edit variant of clip clip_id with options (default: the
    defaults) and queue its job. 404 if the clip does not exist; 422 if it
    is a variant or options name a missing recipe or music; 409 if its
    project has no process job or is archived, or a usage cap is used up."""
    _ready(engine, clip_id)
    try:
        started = start_run(engine, clip_id, options or ProEditOptions())
    except ProEditRunError as error:
        raise _api_error(error) from error
    wake_worker(request)
    return started


@router.get("/runs/{run_id}")
def get_proedit_run(run_id: int, engine: EngineDep) -> ProEditRun:
    """Return run run_id (its job has the progress and ETA); 404 if it does
    not exist."""
    run = get_run(engine, run_id)
    if run is None:
        raise not_found("Pro Edit run", run_id)
    return run


@router.get("/clips/{clip_id}/runs")
def list_proedit_runs(clip_id: int, engine: EngineDep) -> list[ProEditRun]:
    """Return the runs of variant clip_id, newest first; 404 if the clip
    does not exist."""
    with Session(engine) as session:
        clip_row(session, clip_id)
    return list_runs(engine, clip_id)


@router.get("/clips/{clip_id}/plan")
def get_proedit_plan(clip_id: int, engine: EngineDep) -> ProEditPlan:
    """Return the current (newest) plan of variant clip_id; 404 if the clip
    does not exist or has no plan yet."""
    with Session(engine) as session:
        clip_row(session, clip_id)
        plan = current_plan(session, clip_id)
    if plan is None:
        raise ApiError(404, "no_plan", f"clip {clip_id} has no plan yet")
    return plan


@router.get("/clips/{clip_id}/plans")
def list_proedit_plans(clip_id: int, engine: EngineDep) -> list[ProEditPlan]:
    """Return every plan version of variant clip_id, oldest first; 404 if
    the clip does not exist."""
    with Session(engine) as session:
        clip_row(session, clip_id)
        return plan_versions(session, clip_id)


@router.patch("/clips/{clip_id}/plan")
def patch_proedit_plan(
    clip_id: int, body: ProEditItemsUpdate, engine: EngineDep
) -> ProEditPlan:
    """Store the editor's items as the next plan version of variant clip_id
    (changed items become manual) and return it; nothing is rendered. 404
    if the clip does not exist; 422 if it is no variant or the items are not
    valid for it (problems lists why); 409 if a job of it is queued or
    running or it has no plan."""
    with Session(engine) as session:
        clip_row(session, clip_id)
    try:
        return patch_plan(engine, clip_id, body.items)
    except ProEditRunError as error:
        raise _api_error(error) from error


@router.post("/clips/{clip_id}/reset")
def reset_proedit_plan(clip_id: int, engine: EngineDep) -> ProEditPlan:
    """Store a copy of plan version 1 of variant clip_id as its next version
    and return it; nothing is rendered. Errors as for the patch."""
    with Session(engine) as session:
        clip_row(session, clip_id)
    try:
        return reset_plan(engine, clip_id)
    except ProEditRunError as error:
        raise _api_error(error) from error


@router.post("/clips/{clip_id}/regenerate", status_code=202)
def regenerate_proedit(
    clip_id: int,
    request: Request,
    engine: EngineDep,
    options: ProEditOptions | None = None,
) -> ProEditStarted:
    """Queue a job that has the Director plan variant clip_id again with
    options (default: its last run's), then renders it. Errors as for a
    start, plus 422 if the clip is no variant and 409 if a job of it is
    queued or running."""
    return _queue(request, engine, clip_id, "regenerate", options)


@router.post("/clips/{clip_id}/critic", status_code=202)
def rerun_proedit_critic(
    clip_id: int, request: Request, engine: EngineDep
) -> ProEditStarted:
    """Queue a job that runs the critic's rounds on the current plan of
    variant clip_id, then renders it. Errors as for regenerate, plus 409 if
    it has no plan."""
    return _queue(request, engine, clip_id, "critic", None)


@router.post("/clips/{clip_id}/render", status_code=202)
def render_proedit(clip_id: int, request: Request, engine: EngineDep) -> ProEditStarted:
    """Queue a job that renders the current plan of variant clip_id (after
    a patch or reset). Errors as for the critic."""
    return _queue(request, engine, clip_id, "render", None)


@router.get("/clips/{clip_id}/estimate")
def estimate_proedit(
    clip_id: int, engine: EngineDep, options: Annotated[ProEditOptions, Query()]
) -> ProEditEstimate:
    """Return the LLM cost estimate of a Pro Edit of clip clip_id with
    options (no LLM is called). 404 if the clip does not exist; 422 if
    options name a missing recipe or music; 409 if its project has no
    process job or its signals are missing."""
    with Session(engine) as session:
        clip = clip_row(session, clip_id).to_model()
        work = work_dir(session, clip.project_id)
    try:
        return run_estimate(engine, clip, options, work)
    except RunInputError as error:
        raise ApiError(422, "invalid_options", str(error)) from error
    except StepError as error:
        raise ApiError(409, "conflict", str(error)) from error


def _queue(
    request: Request,
    engine: Engine,
    clip_id: int,
    mode: ProEditRunMode,
    options: ProEditOptions | None,
) -> ProEditStarted:
    """Queue a run of mode on variant clip_id (runs.queue_run)."""
    _ready(engine, clip_id)
    try:
        started = queue_run(engine, clip_id, mode, options)
    except ProEditRunError as error:
        raise _api_error(error) from error
    wake_worker(request)
    return started


def _ready(engine: Engine, clip_id: int) -> None:
    """Raise the ApiError that stops a new job on clip clip_id: 404 if it
    does not exist, 409 if its project has no process job or is archived,
    or a usage cap is used up."""
    with Session(engine) as session:
        project_id = clip_row(session, clip_id).project_id
        try:
            require_not_archived(session, project_id)
        except StorageRefused as exc:
            raise ApiError(409, "conflict", str(exc)) from exc
        work_dir(session, project_id)
    require_usage_budget(engine)


def _api_error(error: ProEditRunError) -> ApiError:
    extra = {"problems": error.problems} if error.problems else None
    return ApiError(error.status, error.error, error.message, extra)
