"""The job worker pool (SPEC-v2 2.2): N threads that run the queued jobs.

Each worker thread claims the next queued job (jobs.claim_next: highest
priority first, then oldest) and runs it (jobs.run_claimed). A worker only
claims a job of a kind with a free slot: job_concurrency caps the running
jobs of each kind, and the GPU-heavy kinds share one lock, so at most one job
of all of them runs at a time. The slots are taken under the pool's mutex in
the same step as the claim, so two workers never both fill the last slot.

The defaults come from the settings `workers`, `job_concurrency` and
`gpu_job_kinds` (clipforge.config). start() first queues the jobs that a
stopped process left running (jobs.reset_stale_jobs).
"""

import logging
import threading
from collections import Counter
from collections.abc import Callable, Collection, Mapping
from functools import partial
from pathlib import Path
from typing import get_args

from sqlalchemy import Engine

from clipforge import config
from clipforge.jobs import ClaimedJob, claim_next, reset_stale_jobs, run_claimed
from clipforge.llm import LLMClient
from clipforge.models import JobKind

logger = logging.getLogger(__name__)

# Seconds that an idle worker sleeps before it looks for a job again (wake
# ends the sleep early).
POLL_INTERVAL = 0.5
JOB_KINDS: tuple[str, ...] = get_args(JobKind)

# Runs a claimed job to its end; a failure must not escape (run_claimed).
JobRunner = Callable[[Engine, ClaimedJob], None]


class WorkerPool:
    """Worker threads that run the queued jobs of the job table.

    workers, limits (job kind -> most running jobs) and gpu_kinds default to
    the settings. runner runs a claimed job; it defaults to jobs.run_claimed
    with llm and transcript, which tests and test mode use in place of the
    configured LLM and of whisper. Raises ValueError for a workers count
    below 1 or a limit or GPU kind that is not a job kind.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        workers: int | None = None,
        limits: Mapping[str, int] | None = None,
        gpu_kinds: Collection[str] | None = None,
        poll_interval: float = POLL_INTERVAL,
        llm: LLMClient | None = None,
        transcript: Path | None = None,
        runner: JobRunner | None = None,
    ) -> None:
        settings = config.settings
        self.engine = engine
        self.workers = settings.workers if workers is None else workers
        self.limits = dict(settings.job_concurrency if limits is None else limits)
        self.gpu_kinds = frozenset(
            settings.gpu_job_kinds if gpu_kinds is None else gpu_kinds
        )
        _check_pool(self.workers, self.limits, self.gpu_kinds)
        self.poll_interval = poll_interval
        self.llm = llm
        self.transcript = transcript
        self.runner: JobRunner = runner or partial(
            run_claimed, llm=llm, transcript=transcript
        )
        self._running: Counter[str] = Counter()
        self._mutex = threading.Lock()
        self._gpu = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        """Queue the jobs that a stopped process left running
        (reset_stale_jobs) and start the worker threads.

        Raises RuntimeError if the pool is already started.
        """
        if self._threads:
            raise RuntimeError("the job worker pool is already started")
        reset_stale_jobs(self.engine)
        self._stop.clear()
        self._threads = [
            threading.Thread(
                target=self._loop, name=f"clipforge-jobs-{number}", daemon=True
            )
            for number in range(1, self.workers + 1)
        ]
        for thread in self._threads:
            thread.start()

    def alive(self) -> int:
        """Return the number of worker threads that are running."""
        return sum(thread.is_alive() for thread in self._threads)

    def wake(self) -> None:
        """Make idle workers look for a queued job now, not after
        poll_interval."""
        self._wake.set()

    def stop(self, timeout: float | None = None) -> None:
        """Stop the workers after the jobs they are running and wait up to
        timeout seconds (default: until then) for each thread to end.

        A job still running when the process ends is queued again by the
        next start.
        """
        self._stop.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout)
        self._threads = [thread for thread in self._threads if thread.is_alive()]

    def _loop(self) -> None:
        """Claim and run jobs until stop; sleep when none can be claimed."""
        while not self._stop.is_set():
            try:
                job = self._claim()
            except Exception:
                logger.exception("the job worker pool could not claim a job")
                job = None
            if job is None:
                self._wake.wait(self.poll_interval)
                self._wake.clear()
                continue
            try:
                self.runner(self.engine, job)
            except Exception:
                logger.exception("job %d failed", job.id)
            finally:
                self._release(job.kind)

    def _claim(self) -> ClaimedJob | None:
        """Claim the next queued job of a kind with a free slot and take the
        slot (and the GPU lock for a GPU kind); None if there is none."""
        with self._mutex:
            kinds = [kind for kind in JOB_KINDS if self._has_slot(kind)]
            job = claim_next(self.engine, kinds)
            if job is not None:
                self._running[job.kind] += 1
                if job.kind in self.gpu_kinds:
                    taken = self._gpu.acquire(blocking=False)
                    assert taken, "the GPU lock was free when its slot was checked"
            return job

    def _has_slot(self, kind: str) -> bool:
        """Tell whether a job of kind may start now (call under _mutex)."""
        limit = self.limits.get(kind)
        if limit is not None and self._running[kind] >= limit:
            return False
        return kind not in self.gpu_kinds or not self._gpu.locked()

    def _release(self, kind: str) -> None:
        """Give back the slot (and GPU lock) of a job of kind that ended,
        and wake the idle workers: a job that waited for it may start."""
        with self._mutex:
            self._running[kind] -= 1
            if kind in self.gpu_kinds:
                self._gpu.release()
        self._wake.set()


def _check_pool(workers: int, limits: Mapping[str, int], gpu: Collection[str]) -> None:
    """Raise ValueError unless workers and every limit are at least 1 and
    every kind in limits and gpu is a job kind."""
    if workers < 1:
        raise ValueError(f"workers must be at least 1, not {workers}")
    for kind in [*limits, *gpu]:
        if kind not in JOB_KINDS:
            known = ", ".join(JOB_KINDS)
            raise ValueError(f"unknown job kind {kind!r} (job kinds: {known})")
    for kind, limit in limits.items():
        if limit < 1:
            raise ValueError(f"the {kind} job limit must be at least 1, not {limit}")
