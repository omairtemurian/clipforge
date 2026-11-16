"""Tests of the job worker pool (SPEC-v2 2.2): N workers, priorities,
per-kind concurrency limits, the GPU lock and the atomic claim of a job.

The pool runs real threads on a real SQLite database; only the job body is
replaced by a runner that records how many jobs run at once.
"""

import threading
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from clipforge import config
from clipforge.config import Settings
from clipforge.db import JobRow, ProjectRow, create_db_engine
from clipforge.jobs import ClaimedJob, claim_next
from clipforge.models import JobKind
from clipforge.worker_pool import WorkerPool
from seed import add_project
from sqlalchemy import Engine
from sqlmodel import Session, col, select


def add_jobs(engine: Engine, *specs: tuple[JobKind, int]) -> list[int]:
    """Add a queued job of one project for each (kind, priority) in specs,
    in order; return their ids."""
    project_id = add_project(engine)
    with Session(engine) as session:
        rows = [
            JobRow(
                project_id=project_id,
                kind=kind,
                step="",
                log_path="",
                priority=priority,
            )
            for kind, priority in specs
        ]
        session.add_all(rows)
        session.commit()
        return [row.id for row in rows if row.id is not None]


def statuses(engine: Engine, ids: list[int]) -> list[str]:
    """Return the statuses of jobs ids, in the order of ids."""
    with Session(engine) as session:
        return [session.get_one(JobRow, job_id).status for job_id in ids]


class Recorder:
    """A job runner that holds each job for `hold` seconds (or until all
    parties reached `barrier`), then marks it done; it records the order of
    the jobs and the most jobs (per kind and in all) that ran at once."""

    def __init__(
        self, hold: float = 0.05, barrier: threading.Barrier | None = None
    ) -> None:
        self.hold = hold
        self.barrier = barrier
        self.order: list[int] = []
        self.peak: Counter[str] = Counter()
        self._running: Counter[str] = Counter()
        self._lock = threading.Lock()

    def __call__(self, engine: Engine, job: ClaimedJob) -> None:
        with self._lock:
            self.order.append(job.id)
            self._running[job.kind] += 1
            self._running["all"] += 1
            for key in (job.kind, "all"):
                self.peak[key] = max(self.peak[key], self._running[key])
        if self.barrier is not None:
            self.barrier.wait(timeout=10)
        else:
            time.sleep(self.hold)
        with self._lock:
            self._running[job.kind] -= 1
            self._running["all"] -= 1
        with Session(engine) as session:
            session.get_one(JobRow, job.id).status = "done"
            session.commit()


@contextmanager
def running(pool: WorkerPool) -> Iterator[WorkerPool]:
    """Start pool and stop it on exit."""
    pool.start()
    try:
        yield pool
    finally:
        pool.stop(timeout=10)


def wait_done(engine: Engine, ids: list[int], timeout: float = 20) -> None:
    """Wait until jobs ids are done; fail the test after timeout seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if statuses(engine, ids) == ["done"] * len(ids):
            return
        time.sleep(0.01)
    pytest.fail(f"jobs did not end: {statuses(engine, ids)}")


def test_the_workers_setting_starts_n_worker_threads(
    engine: Engine, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WORKERS", raising=False)
    assert Settings(data_dir=data_dir).workers == 2
    monkeypatch.setenv("WORKERS", "3")
    monkeypatch.setattr(config, "settings", Settings(data_dir=data_dir))
    assert config.settings.workers == 3

    pool = WorkerPool(engine, poll_interval=0.01)
    with running(pool):
        assert pool.alive() == 3
        names = {thread.name for thread in threading.enumerate()}
        assert {"clipforge-jobs-1", "clipforge-jobs-2", "clipforge-jobs-3"} <= names
    assert pool.alive() == 0


def test_claim_next_takes_the_highest_priority_then_the_oldest(
    engine: Engine,
) -> None:
    ids = add_jobs(
        engine,
        ("process", 0),
        ("render", 5),
        ("process", -1),
        ("process", 5),
        ("render", 10),
    )

    claimed = [claim_next(engine) for _ in ids]

    assert [job.id for job in claimed if job is not None] == [
        ids[4],
        ids[1],
        ids[3],
        ids[0],
        ids[2],
    ]
    assert claim_next(engine) is None
    assert statuses(engine, ids) == ["running"] * 5


def test_claim_next_only_takes_the_given_kinds(engine: Engine) -> None:
    process_id, render_id = add_jobs(engine, ("process", 9), ("render", 0))

    assert claim_next(engine, []) is None
    job = claim_next(engine, ["render"])
    assert job is not None
    assert (job.id, job.kind, job.clip_id) == (render_id, "render", None)
    assert claim_next(engine, ["render"]) is None
    assert statuses(engine, [process_id, render_id]) == ["queued", "running"]

    job = claim_next(engine, ["process", "render"])
    assert job is not None and job.id == process_id
    with Session(engine) as session:
        assert session.get_one(ProjectRow, job.project_id).status == "running"


def test_the_pool_runs_higher_priority_jobs_first(engine: Engine) -> None:
    ids = add_jobs(engine, ("render", 0), ("render", 3), ("process", 7))
    recorder = Recorder(hold=0.01)

    with running(WorkerPool(engine, workers=1, runner=recorder, poll_interval=0.01)):
        wait_done(engine, ids)

    assert recorder.order == [ids[2], ids[1], ids[0]]


def test_gpu_kinds_share_one_lock(engine: Engine) -> None:
    ids = add_jobs(engine, ("process", 0), ("render", 0), ("process", 0))
    recorder = Recorder(hold=0.1)
    pool = WorkerPool(
        engine,
        workers=3,
        limits={"process": 3, "render": 3},
        gpu_kinds=["process", "render"],
        runner=recorder,
        poll_interval=0.01,
    )

    with running(pool):
        wait_done(engine, ids)

    assert sorted(recorder.order) == ids
    assert recorder.peak["all"] == 1


def test_without_the_gpu_lock_the_same_jobs_run_at_once(engine: Engine) -> None:
    ids = add_jobs(engine, ("process", 0), ("render", 0), ("process", 0))
    recorder = Recorder(barrier=threading.Barrier(3))
    pool = WorkerPool(
        engine,
        workers=3,
        limits={"process": 3, "render": 3},
        gpu_kinds=[],
        runner=recorder,
        poll_interval=0.01,
    )

    with running(pool):
        wait_done(engine, ids)

    assert recorder.peak["all"] == 3


def test_a_kind_limit_caps_its_running_jobs(engine: Engine) -> None:
    ids = add_jobs(
        engine,
        ("render", 0),
        ("render", 0),
        ("render", 0),
        ("process", 0),
        ("process", 0),
    )
    recorder = Recorder(hold=0.1)
    pool = WorkerPool(
        engine,
        workers=3,
        limits={"render": 1},
        gpu_kinds=[],
        runner=recorder,
        poll_interval=0.01,
    )

    with running(pool):
        wait_done(engine, ids)

    assert recorder.peak["render"] == 1
    assert recorder.peak["all"] >= 2


def test_with_the_default_settings_a_render_runs_next_to_a_gpu_job(
    engine: Engine,
) -> None:
    assert config.settings.gpu_job_kinds == ["process", "reprompt"]
    ids = add_jobs(engine, ("process", 0), ("render", 0))
    recorder = Recorder(barrier=threading.Barrier(2))

    with running(WorkerPool(engine, runner=recorder, poll_interval=0.01)):
        wait_done(engine, ids)

    assert recorder.peak["all"] == 2


def test_a_failing_runner_frees_its_slot_and_gpu_lock(engine: Engine) -> None:
    ids = add_jobs(engine, ("process", 1), ("process", 0))
    recorder = Recorder(hold=0.01)

    def runner(engine: Engine, job: ClaimedJob) -> None:
        if job.id == ids[0]:
            raise RuntimeError("boom")
        recorder(engine, job)

    pool = WorkerPool(engine, workers=2, runner=runner, poll_interval=0.01)
    with running(pool):
        wait_done(engine, ids[1:])

    assert recorder.order == [ids[1]]


def test_two_workers_never_claim_the_same_job(engine: Engine) -> None:
    ids = add_jobs(engine, *[("process", n % 3) for n in range(150)])
    threads_count = 8
    barrier = threading.Barrier(threads_count)
    claimed: list[list[int]] = [[] for _ in range(threads_count)]
    errors: list[BaseException] = []

    def claim_all(index: int) -> None:
        """Claim one job per round, all threads at once, until past the end."""
        own = create_db_engine()
        try:
            for _ in range(len(ids) // threads_count + 2):
                barrier.wait(timeout=10)
                if (job := claim_next(own)) is not None:
                    claimed[index].append(job.id)
        except BaseException as exc:
            errors.append(exc)
        finally:
            own.dispose()

    workers = [
        threading.Thread(target=claim_all, args=(index,))
        for index in range(threads_count)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=60)

    assert errors == []
    every = [job_id for own in claimed for job_id in own]
    assert len(every) == len(set(every)) == len(ids)
    assert sorted(every) == ids
    assert all(claimed)
    with Session(engine) as session:
        assert (
            session.exec(select(JobRow.id).where(col(JobRow.status) != "running")).all()
            == []
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"workers": 0}, "workers must be at least 1, not 0"),
        ({"limits": {"upload": 1}}, "unknown job kind 'upload'"),
        ({"gpu_kinds": ["tts"]}, "unknown job kind 'tts'"),
        ({"limits": {"render": 0}}, "the render job limit must be at least 1"),
    ],
)
def test_a_bad_pool_setting_is_rejected(
    engine: Engine, kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        WorkerPool(engine, **kwargs)  # type: ignore[arg-type]
