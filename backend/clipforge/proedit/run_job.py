"""The "proedit" job (SPEC-v3 3.8): one Pro Edit run on a variant, with the
shared progress and ETA (job_progress.PROEDIT_STEPS):

1. plan (start, regenerate): the Director plans the variant from the run's
   options (run_inputs.director_request; the rule-based Director when the
   LLM fails, with the reason in the run's notes); the plan is stored as
   the variant's next version and every item its post-processing moved or
   dropped (and every composite move left out) is a note (DirectorResult.edit_notes). A
   start that resumes after the app stopped keeps the plan it already
   stored.
2. proxy, critic (start and regenerate with use_critic, critic): the critic
   loop judges proxies of the plan (critic.revise.critic_loop); "proxy" is
   the first proxy's render, "critic" goes from round 1 to N (the run's
   rounds count the finished ones); each revision is stored as a version.
   Why the critic stopped early (no vision, the cap, a failure) is a note.
3. final: the plan is rendered as the variant's video (run_render).

A render run is step 3 alone on the current plan (the overall progress
starts at the final step). The run ends done with its plan, critic rounds
and scores, the estimated and spent USD (None: no priced LLM call) and its
notes; on any error it fails with the error (a variant left rendering
fails too) and the error is raised for the job to fail.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, select

from clipforge import config, notifications
from clipforge.db import ClipRow, JobRow
from clipforge.job_rows import (
    process_work_dir,
    progress_writer,
    record_progress,
    save_progress,
    set_step,
)
from clipforge.joblog import job_log
from clipforge.llm import LLMClient, create_client
from clipforge.models import (
    Clip,
    CriticRound,
    ProEditOptions,
    ProEditPlan,
    ProEditRunMode,
)
from clipforge.pipeline.step import StepError, job_dir
from clipforge.proedit.critic.revise import critic_loop
from clipforge.proedit.director_cost import CostEstimate
from clipforge.proedit.director_llm import director_plan
from clipforge.proedit.director_prompt import DirectorRequest
from clipforge.proedit.plan_store import current_plan, get_plan, save_plan
from clipforge.proedit.render.cutout import cutout_choice
from clipforge.proedit.rows import ProEditRunRow
from clipforge.proedit.run_inputs import director_request
from clipforge.proedit.run_render import ensure_variant_crop, render_final, render_proxy
from clipforge.proedit.runs import variant_options


@dataclass
class _Outcome:
    """What the run did so far (what its row gets)."""

    plan: ProEditPlan | None = None
    notes: list[str] = field(default_factory=list)
    estimate: float | None = None
    spent: float | None = None
    rounds: list[CriticRound] = field(default_factory=list)

    def cost(
        self, estimate: CostEstimate | None, spent: float | None, n: int = 1
    ) -> None:
        if estimate is not None and estimate.max_usd is not None:
            self.estimate = (self.estimate or 0.0) + estimate.max_usd * n
        if spent is not None:
            self.spent = (self.spent or 0.0) + spent


@dataclass
class _Job:
    """The job's context: its engine and ids, the variant and its work
    directory, the run's mode and options and the LLM."""

    engine: Engine
    job_id: int
    run_id: int
    project_id: int
    clip: Clip
    work: Path
    mode: ProEditRunMode
    options: ProEditOptions
    llm: LLMClient
    resume_plan_id: int | None


def run_proedit_job(
    engine: Engine, job_id: int, *, llm: LLMClient | None = None
) -> None:
    """Run "proedit" job job_id (module docstring) with llm (default: the
    configured client). Raises StepError if the job has no run, and the
    error that failed the run."""
    with Session(engine) as session:
        log_path = Path(session.get_one(JobRow, job_id).log_path)
        run = session.exec(
            select(ProEditRunRow).where(ProEditRunRow.job_id == job_id)
        ).first()
        if run is None or run.id is None:
            raise StepError(f"job {job_id} has no Pro Edit run")
        run_id, clip_id = run.id, run.clip_id
    try:
        with job_log(log_path):
            job = _start(engine, job_id, run_id, llm or create_client())
            outcome = _run(job)
    except Exception as error:
        _failed(engine, run_id, clip_id, str(error))
        raise
    _done(engine, job, outcome)


def _start(engine: Engine, job_id: int, run_id: int, llm: LLMClient) -> _Job:
    """Mark run run_id of job job_id running and return the job's context."""
    with Session(engine) as session:
        job = session.get_one(JobRow, job_id)
        run = session.get_one(ProEditRunRow, run_id)
        work = process_work_dir(session, job.project_id)
        options = run.options or variant_options(session, run.clip_id)
        run.status, run.error = "running", None
        run.started_at, run.finished_at = datetime.now(UTC), None
        session.add(run)
        session.commit()
        clip = session.get_one(ClipRow, run.clip_id).to_model()
        return _Job(
            engine=engine,
            job_id=job_id,
            run_id=run_id,
            project_id=job.project_id,
            clip=clip,
            work=work,
            mode=run.mode,
            options=options,
            llm=llm,
            resume_plan_id=run.plan_id,
        )


def _run(job: _Job) -> _Outcome:
    """Run the steps of job's mode and return what they did."""
    outcome = _Outcome()
    ensure_variant_crop(job.engine, job.clip, job.work)
    request: DirectorRequest | None = None
    if job.mode in ("start", "regenerate"):
        request = _plan(job, outcome)
    else:
        with Session(job.engine) as session:
            outcome.plan = current_plan(session, job.clip.id)
        if outcome.plan is None:
            raise StepError(f"clip {job.clip.id} has no plan to {job.mode}")
    assert outcome.plan is not None
    if job.mode == "critic" or (job.mode != "render" and job.options.use_critic):
        if request is None:
            request = director_request(job.engine, job.clip, job.options, job.work)
        _critic(job, request, outcome)
    set_step(job.engine, job.job_id, "final")
    render_final(
        job.engine,
        job.work,
        job.clip.id,
        outcome.plan,
        progress_writer(job.engine, job.job_id),
        cutout_choice(job.options),
    )
    return outcome


def _plan(job: _Job, outcome: _Outcome) -> DirectorRequest:
    """Step 1: store the Director's plan as outcome's plan (a resumed start
    keeps its plan) and return the request it was made from."""
    set_step(job.engine, job.job_id, "plan")
    request = director_request(job.engine, job.clip, job.options, job.work)
    with Session(job.engine) as session:
        if job.mode == "start" and job.resume_plan_id is not None:
            outcome.plan = get_plan(session, job.resume_plan_id)
            if outcome.plan is not None:
                return request
        result = director_plan(
            request, job.llm, engine=job.engine, project_id=job.project_id
        )
        outcome.plan = save_plan(session, result.plan)
    outcome.cost(result.estimate, result.cost_usd)
    if result.fallback is not None:
        outcome.notes.append(
            f"The rule-based Director made the plan: {result.fallback}."
        )
    outcome.notes += result.edit_notes()
    _update_run(job, plan_id=outcome.plan.id)
    return request


def _critic(job: _Job, request: DirectorRequest, outcome: _Outcome) -> None:
    """Step 2: run the critic loop on outcome's plan (module docstring)."""
    assert outcome.plan is not None
    folder = job_dir(job.job_id)
    folder.mkdir(parents=True, exist_ok=True)
    state = {"round": 0}

    def on_round(n: int, total: int) -> None:
        state["round"] = n
        if n == 1:
            set_step(job.engine, job.job_id, "proxy")
        else:
            save_progress(job.engine, job.job_id, (n - 1) / total)
            _update_run(job, rounds=n - 1)

    def render(plan: ProEditPlan) -> Path:
        first = state["round"] == 1
        writer = progress_writer(job.engine, job.job_id) if first else None
        proxy = render_proxy(
            job.engine,
            job.work,
            folder,
            job.clip,
            plan,
            writer,
            cutout_choice(job.options),
        )
        if first:
            set_step(job.engine, job.job_id, "critic")
        return proxy

    def store(plan: ProEditPlan) -> ProEditPlan:
        with Session(job.engine) as session:
            saved = save_plan(session, plan)
        _update_run(job, plan_id=saved.id)
        return saved

    loop = critic_loop(
        outcome.plan,
        request,
        render,
        job.llm,
        engine=job.engine,
        project_id=job.project_id,
        store=store,
        on_round=on_round,
    )
    outcome.plan = loop.plan
    outcome.rounds = loop.rounds
    outcome.cost(
        loop.estimate, loop.cost_usd, config.settings.proedit.critic_max_rounds
    )
    if loop.message:
        outcome.notes.append(loop.message)
    elif loop.stopped == "off":
        outcome.notes.append("The critic is off (proedit.critic_max_rounds is 0).")


def _update_run(job: _Job, **changes: object) -> None:
    """Set fields of job's run while it runs."""
    with Session(job.engine) as session:
        run = session.get_one(ProEditRunRow, job.run_id)
        for name, value in changes.items():
            setattr(run, name, value)
        session.add(run)
        session.commit()


def _done(engine: Engine, job: _Job, outcome: _Outcome) -> None:
    """Mark the run done with outcome and the job done."""
    assert outcome.plan is not None
    with Session(engine) as session:
        run = session.get_one(ProEditRunRow, job.run_id)
        run.status, run.finished_at = "done", datetime.now(UTC)
        run.plan_id = outcome.plan.id
        run.critic_scores, run.rounds = outcome.rounds, len(outcome.rounds)
        run.cost_estimate, run.cost_actual = outcome.estimate, outcome.spent
        run.notes = outcome.notes
        session.add(run)
        row = session.get_one(JobRow, job.job_id)
        record_progress(session, row, "final", 1.0)
        row.status = "done"
        session.commit()


def _failed(engine: Engine, run_id: int, clip_id: int, error: str) -> None:
    """Mark run run_id failed with error; clip clip_id fails if it was left
    rendering."""
    with Session(engine) as session:
        run = session.get_one(ProEditRunRow, run_id)
        run.status, run.error, run.finished_at = "failed", error, datetime.now(UTC)
        session.add(run)
        clip = session.get_one(ClipRow, clip_id)
        failed = clip.status == "rendering"
        if failed:
            clip.status, clip.output_path = "failed", None
            session.add(clip)
        session.commit()
    if failed:
        notifications.render_failed(engine, clip_id)
