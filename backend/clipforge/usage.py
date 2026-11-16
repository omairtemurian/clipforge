"""The usage meter (SPEC-v2 2.4): what ClipForge's jobs use, by month.

Three kinds of use are metered, as UsageRecord rows: COMPUTE (seconds that a
worker spent on a job), LLM_TOKENS (tokens that an LLM answer reports) and
API_CALLS (calls of any other paid API, such as stock footage or TTS). A job
runs inside job_usage(), which records its compute time and lets the LLM
clients record their tokens for the job's project (recording()); a client
used outside any of them records nothing.

month_summary() totals a calendar month (UTC) per kind and per project.
Monthly caps are settings (usage_cap_*; 0 = none): check_caps() raises
UsageCapExceeded once a kind's total this month reached its cap, and the
API answers 409 to a new job.

Metering never fails a job: a record that cannot be written is logged.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime

from pydantic import BaseModel
from sqlalchemy import Engine, func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, select

from clipforge import config
from clipforge.asset_rows import UsageRecordRow
from clipforge.config import Settings

logger = logging.getLogger(__name__)

COMPUTE = "compute"
LLM_TOKENS = "llm_tokens"
API_CALLS = "api_calls"
USAGE_KINDS = (COMPUTE, LLM_TOKENS, API_CALLS)
SECONDS_PER_HOUR = 3600


class UsageCapExceeded(RuntimeError):
    """A monthly cap is used up; the message says which and how to go on."""


class KindUsage(BaseModel):
    """The month's total of one kind: units (seconds for compute), the cost in
    USD of the paid records (None if no record has a cost), the monthly cap in
    the same units (None if there is none) and whether the total reached it."""

    kind: str
    units: float
    cost_usd: float | None
    cap: float | None
    exceeded: bool


class ProjectUsage(BaseModel):
    """The month's total of one kind for one project; project_id is None for
    use outside a project (or of a deleted one)."""

    project_id: int | None
    kind: str
    units: float
    cost_usd: float | None


class UsageSummary(BaseModel):
    """GET /api/usage: the month ("YYYY-MM"), its totals per kind (every
    metered kind, then any other recorded) and per project and kind."""

    month: str
    kinds: list[KindUsage]
    projects: list[ProjectUsage]


@dataclass(frozen=True)
class Recorder:
    """Where the metered clients of this context (LLM clients, platform
    quota guards) record their use: LLM tokens as kind, at usd_per_token
    (None: no cost), each answer's tokens also appended to tally if given."""

    engine: Engine
    project_id: int | None
    kind: str = LLM_TOKENS
    usd_per_token: float | None = None
    tally: list[int] | None = None


_recorder: ContextVar[Recorder | None] = ContextVar("usage_recorder", default=None)


def utc_now() -> datetime:
    """Return the current time, timezone-aware (the database needs that)."""
    return datetime.now(UTC)


def record(
    engine: Engine,
    kind: str,
    units: float,
    *,
    project_id: int | None = None,
    cost_usd: float | None = None,
    at: datetime | None = None,
) -> None:
    """Add a UsageRecord of units of kind (at the given time, default now).

    A record that cannot be written is logged, not raised.
    """
    row = UsageRecordRow(
        project_id=project_id,
        kind=kind,
        units=units,
        cost_usd=cost_usd,
        at=utc_now() if at is None else at,
    )
    try:
        with Session(engine) as session:
            session.add(row)
            session.commit()
    except SQLAlchemyError:
        logger.exception("could not record %s usage of %s", kind, units)


def current() -> Recorder | None:
    """Return the recording() context of the caller, None outside one."""
    return _recorder.get()


def record_tokens(tokens: int | None) -> None:
    """Record the tokens of one LLM answer for the current recording()
    context; nothing if there is none or the answer reported no tokens."""
    recorder = _recorder.get()
    if recorder is None or not tokens:
        return
    price = recorder.usd_per_token
    record(
        recorder.engine,
        recorder.kind,
        tokens,
        project_id=recorder.project_id,
        cost_usd=None if price is None else tokens * price,
    )
    if recorder.tally is not None:
        recorder.tally.append(tokens)


@contextmanager
def recording(
    engine: Engine,
    project_id: int | None,
    *,
    kind: str = LLM_TOKENS,
    usd_per_token: float | None = None,
    tally: list[int] | None = None,
) -> Iterator[None]:
    """Let the LLM clients used inside record their tokens for project_id
    (None: outside a project) in engine's database, as kind (Pro Edit's own
    category, for one) at usd_per_token, and append each answer's tokens to
    tally if given."""
    token = _recorder.set(Recorder(engine, project_id, kind, usd_per_token, tally))
    try:
        yield
    finally:
        _recorder.reset(token)


@contextmanager
def job_usage(engine: Engine, project_id: int) -> Iterator[None]:
    """Meter a job of project_id: record the seconds it took as COMPUTE when
    the block ends, however it ends, and its LLM tokens as they come."""
    started = time.monotonic()
    with recording(engine, project_id):
        try:
            yield
        finally:
            record(engine, COMPUTE, time.monotonic() - started, project_id=project_id)


def month_start(day: date) -> datetime:
    """Return the first instant (UTC) of the month of day."""
    return datetime(day.year, day.month, 1, tzinfo=UTC)


def next_month_start(day: date) -> datetime:
    """Return the first instant of the month after the one of day."""
    start = month_start(day)
    return datetime(start.year + start.month // 12, start.month % 12 + 1, 1, tzinfo=UTC)


def parse_month(month: str) -> date:
    """Return the first day of month, "YYYY-MM"; raises ValueError if it is
    not one."""
    return datetime.strptime(month, "%Y-%m").date()


def caps_of(cfg: Settings) -> dict[str, float]:
    """Return the monthly caps of cfg by kind, in the units of the records
    (seconds for compute); a kind with no cap is left out."""
    caps = {
        COMPUTE: cfg.usage_cap_compute_hours * SECONDS_PER_HOUR,
        LLM_TOKENS: cfg.usage_cap_llm_tokens,
        API_CALLS: cfg.usage_cap_api_calls,
    }
    return {kind: cap for kind, cap in caps.items() if cap > 0}


def month_summary(
    engine: Engine, month: date, cfg: Settings | None = None
) -> UsageSummary:
    """Return the totals of the month of `month`, with the caps of cfg
    (default: the app settings)."""
    caps = caps_of(config.settings if cfg is None else cfg)
    in_month = (
        col(UsageRecordRow.at) >= month_start(month),
        col(UsageRecordRow.at) < next_month_start(month),
    )
    units = func.sum(UsageRecordRow.units)
    cost = func.sum(UsageRecordRow.cost_usd)
    with Session(engine) as session:
        per_project = session.exec(
            select(UsageRecordRow.project_id, UsageRecordRow.kind, units, cost)
            .where(*in_month)
            .group_by(col(UsageRecordRow.project_id), col(UsageRecordRow.kind))
            .order_by(col(UsageRecordRow.project_id), col(UsageRecordRow.kind))
        ).all()
    projects = [
        ProjectUsage(project_id=pid, kind=kind, units=total, cost_usd=spent)
        for pid, kind, total, spent in per_project
    ]
    totals: dict[str, tuple[float, float | None]] = {
        kind: (0.0, None) for kind in USAGE_KINDS
    }
    for item in projects:
        done, spent = totals.get(item.kind, (0.0, None))
        if item.cost_usd is not None:
            spent = (spent or 0.0) + item.cost_usd
        totals[item.kind] = (done + item.units, spent)
    kinds = [
        KindUsage(
            kind=kind,
            units=done,
            cost_usd=spent,
            cap=caps.get(kind),
            exceeded=kind in caps and done >= caps[kind],
        )
        for kind, (done, spent) in totals.items()
    ]
    return UsageSummary(month=f"{month:%Y-%m}", kinds=kinds, projects=projects)


def describe(kind: str, units: float) -> str:
    """Return units of kind for a sentence: "2.50 compute hours"."""
    if kind == COMPUTE:
        return f"{units / SECONDS_PER_HOUR:.2f} compute hours"
    names = {LLM_TOKENS: "LLM tokens", API_CALLS: "API calls"}
    return f"{units:,.0f} {names.get(kind, kind)}"


def check_caps(
    engine: Engine, cfg: Settings | None = None, now: datetime | None = None
) -> None:
    """Raise UsageCapExceeded if a monthly cap is used up this month (the
    month of now, default the current time); do nothing if none is set."""
    cfg = config.settings if cfg is None else cfg
    if not caps_of(cfg):
        return
    today = (utc_now() if now is None else now).date()
    summary = month_summary(engine, today, cfg)
    for item in summary.kinds:
        if item.exceeded and item.cap is not None:
            raise UsageCapExceeded(
                f"The monthly cap of {describe(item.kind, item.cap)} is used up "
                f"({describe(item.kind, item.units)} in {summary.month}). "
                "Raise or remove the cap in Settings to start new jobs."
            )
