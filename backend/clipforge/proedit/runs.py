"""Pro Edit runs (SPEC-v3 3.8, 0.13): what the API asks of Pro Edit.

A start copies the clip as a new variant (variant "pro_edit", linked by
parent_clip_id, status rendering) and queues a "proedit" job that plans
and renders it (proedit/run_job.py); the original clip is never changed.
On a variant, regenerate (a new plan from the Director), critic (the
critic's rounds on the current plan) and render (the current plan) queue
a job of their own; one job at a time per variant.

The editor's changes need no job: a patch stores the edited items as the
next plan version (made by the user; every changed or new item becomes
manual) once they are valid for the clip, and a reset stores a copy of
version 1 as the next version. Neither renders: the editor asks for that.

ProEditRunError carries the HTTP status, error code and message the API
answers with (problems: what makes edited items invalid).
"""

from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge import config
from clipforge.clip_split import duplicate_clip
from clipforge.db import ClipRow, JobRow
from clipforge.models import (
    EdlItem,
    ProEditOptions,
    ProEditPlan,
    ProEditRun,
    ProEditRunMode,
    ProEditStarted,
)
from clipforge.pipeline.step import job_dir
from clipforge.process import JOB_LOG
from clipforge.proedit.director_catalog import catalog_problems
from clipforge.proedit.edl import plan_problems
from clipforge.proedit.plan_store import current_plan, first_plan, save_plan
from clipforge.proedit.rows import ProEditRunRow
from clipforge.proedit.run_inputs import RunInputError, catalog, check_options
from clipforge.timeline import clip_length

TITLE_SUFFIX = " — Pro Edit"
ACTIVE = ("queued", "running")


class ProEditRunError(Exception):
    """A request Pro Edit refuses: status (HTTP), error (code), message and
    problems (the invalid items of a patch)."""

    def __init__(
        self, status: int, error: str, message: str, problems: list[str] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message
        self.problems = problems or []


def start_run(engine: Engine, clip_id: int, options: ProEditOptions) -> ProEditStarted:
    """Make a Pro Edit variant of clip clip_id with options and queue its
    job (module docstring). Raises ProEditRunError (422) if the clip is a
    variant itself or options name a missing recipe or music."""
    with Session(engine) as session:
        row = session.get_one(ClipRow, clip_id)
        if row.variant != "original":
            raise ProEditRunError(
                422, "not_an_original", f"clip {clip_id} is a variant itself"
            )
        _check(session, options)
        variant = duplicate_clip(
            session,
            row,
            {
                "title": f"{row.title}{TITLE_SUFFIX}",
                "parent_clip_id": clip_id,
                "variant": "pro_edit",
                "status": "rendering",
            },
        )
        return _queue(session, variant, "start", options)


def queue_run(
    engine: Engine,
    clip_id: int,
    mode: ProEditRunMode,
    options: ProEditOptions | None = None,
) -> ProEditStarted:
    """Queue a job of mode (regenerate, critic or render) on variant
    clip_id; regenerate plans with options (default: the variant's last).
    Raises ProEditRunError if the clip is no Pro Edit variant (422), a job
    of it is queued or running (409), it has no plan to judge or render
    (409) or options name a missing recipe or music (422)."""
    with Session(engine) as session:
        row = _variant(session, clip_id)
        _not_busy(session, clip_id)
        if mode != "regenerate" and current_plan(session, clip_id) is None:
            raise ProEditRunError(409, "no_plan", f"clip {clip_id} has no plan yet")
        chosen = options if options is not None else variant_options(session, clip_id)
        _check(session, chosen)
        return _queue(session, row, mode, chosen)


def get_run(engine: Engine, run_id: int) -> ProEditRun | None:
    """Return run run_id, None if there is none."""
    with Session(engine) as session:
        row = session.get(ProEditRunRow, run_id)
        return None if row is None else row.to_model()


def list_runs(engine: Engine, clip_id: int) -> list[ProEditRun]:
    """Return the runs of clip clip_id, newest first."""
    with Session(engine) as session:
        rows = session.exec(
            select(ProEditRunRow)
            .where(ProEditRunRow.clip_id == clip_id)
            .order_by(col(ProEditRunRow.id).desc())
        ).all()
        return [row.to_model() for row in rows]


def variant_options(session: Session, clip_id: int) -> ProEditOptions:
    """Return the options of the variant's last run that had some, else its
    current plan's preset, intensity and recipe, else the defaults."""
    last = session.exec(
        select(ProEditRunRow)
        .where(ProEditRunRow.clip_id == clip_id)
        .where(col(ProEditRunRow.options).is_not(None))
        .order_by(col(ProEditRunRow.id).desc())
    ).first()
    if last is not None and last.options is not None:
        return last.options
    plan = current_plan(session, clip_id)
    if plan is None:
        return ProEditOptions()
    return ProEditOptions(
        preset=plan.preset,
        intensity=plan.intensity,
        style_recipe_id=plan.style_recipe_id,
    )


def patch_plan(engine: Engine, clip_id: int, items: list[EdlItem]) -> ProEditPlan:
    """Store items as the next plan version of variant clip_id (module
    docstring) and return it. Raises ProEditRunError if the clip is no
    variant (422), is busy or has no plan (409), or items are not valid for
    it (422 invalid_plan with the problems)."""
    with Session(engine) as session:
        row = _variant(session, clip_id)
        _not_busy(session, clip_id)
        current = _current(session, clip_id)
        before = {item.id: item for item in current.items}
        edited = [_marked(item, before.get(item.id)) for item in items]
        try:
            plan = ProEditPlan.model_validate(
                current.model_dump() | {"items": edited, "created_by": "user"}
            )
        except ValidationError as error:
            problems = [str(e["msg"]) for e in error.errors()]
            raise _invalid(problems) from error
        problems = plan_problems(plan, clip_length(row.to_model(), _fps()))
        problems += catalog_problems(plan.items, catalog(session))
        if problems:
            raise _invalid(problems)
        return save_plan(session, plan, "user")


def reset_plan(engine: Engine, clip_id: int) -> ProEditPlan:
    """Store a copy of plan version 1 of variant clip_id as its next version
    and return it. Raises ProEditRunError like patch_plan."""
    with Session(engine) as session:
        _variant(session, clip_id)
        _not_busy(session, clip_id)
        first = first_plan(session, clip_id)
        if first is None:
            raise ProEditRunError(409, "no_plan", f"clip {clip_id} has no plan yet")
        return save_plan(session, first, "user")


def fail_job_runs(session: Session, job_id: int, error: str) -> None:
    """Mark the unfinished runs of job job_id failed with error (the job
    stopped the app too often); the caller commits."""
    rows = session.exec(
        select(ProEditRunRow)
        .where(ProEditRunRow.job_id == job_id)
        .where(col(ProEditRunRow.status).in_(ACTIVE))
    ).all()
    for row in rows:
        row.status, row.error = "failed", error
        row.finished_at = datetime.now(UTC)
        session.add(row)


def _queue(
    session: Session, clip: ClipRow, mode: ProEditRunMode, options: ProEditOptions
) -> ProEditStarted:
    """Add the job and run of mode on clip with options and commit."""
    assert clip.id is not None
    job = JobRow(
        project_id=clip.project_id,
        clip_id=clip.id,
        kind="proedit",
        step="",
        log_path="",
    )
    session.add(job)
    session.flush()
    assert job.id is not None
    job.log_path = str(job_dir(job.id) / JOB_LOG)
    run = ProEditRunRow(clip_id=clip.id, job_id=job.id, mode=mode, options=options)
    session.add(run)
    session.commit()
    session.refresh(run)
    session.refresh(clip)
    return ProEditStarted(clip=clip.to_model(), run=run.to_model(), job_id=job.id)


def _check(session: Session, options: ProEditOptions) -> None:
    try:
        check_options(session, options)
    except RunInputError as error:
        raise ProEditRunError(422, "invalid_options", str(error)) from error


def _variant(session: Session, clip_id: int) -> ClipRow:
    row = session.get_one(ClipRow, clip_id)
    if row.variant != "pro_edit":
        raise ProEditRunError(
            422, "not_a_proedit_variant", f"clip {clip_id} is not a Pro Edit variant"
        )
    return row


def _not_busy(session: Session, clip_id: int) -> None:
    busy = session.exec(
        select(ProEditRunRow.id)
        .where(ProEditRunRow.clip_id == clip_id)
        .where(col(ProEditRunRow.status).in_(ACTIVE))
    ).first()
    if busy is not None:
        raise ProEditRunError(
            409, "proedit_busy", f"run {busy} of clip {clip_id} is not finished yet"
        )


def _current(session: Session, clip_id: int) -> ProEditPlan:
    plan = current_plan(session, clip_id)
    if plan is None:
        raise ProEditRunError(409, "no_plan", f"clip {clip_id} has no plan yet")
    return plan


def _marked(item: EdlItem, before: EdlItem | None) -> EdlItem:
    """item as the editor sent it: manual unless it is unchanged."""
    if before is not None and before.model_copy(update={"source": item.source}) == item:
        return item.model_copy(update={"source": before.source})
    return item.model_copy(update={"source": "manual"})


def _invalid(problems: list[str]) -> ProEditRunError:
    return ProEditRunError(
        422, "invalid_plan", "the plan is not valid: " + "; ".join(problems), problems
    )


def _fps() -> int:
    return config.settings.render.fps
