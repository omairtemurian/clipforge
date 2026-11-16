"""One overall progress and an ETA for a job, across all of its steps.

Each step of a job weighs its measured share of the whole run
(Settings.step_weights: transcribe and render are the heavy ones). A step
reports its own progress from 0 to 1 from real work (yt-dlp bytes, ffmpeg
-progress out_time, transcribed audio seconds, clips rendered), so the
overall progress is the weight of the finished steps plus the current
step's weight times its progress, over the weight of the steps the job runs.

The ETA divides the work that is left (in overall progress) by the rate the
current step measured, and is smoothed exponentially. It stays unknown until
the job has run MIN_DATA_SECONDS.
"""

import time
from collections.abc import Callable, Mapping

from clipforge import config
from clipforge.models import JobKind

# The steps of each kind of job, in the order they run.
PROCESS_STEPS = (
    "ingest",
    "transcribe",
    "signals",
    "visuals",
    "enrich",
    "curate",
    "score",
    "snap",
    "reframe",
    "render",
)
REPROMPT_STEPS = ("visuals", "curate", "score", "snap", "reframe", "render")
RENDER_STEPS = ("render",)
# A Pro Edit job (proedit/run_job.py): the Director's plan, the first proxy
# render, the critic's rounds (their own proxies included), the final render.
PROEDIT_STEPS = ("plan", "proxy", "critic", "final")
# The weight of a step that Settings.step_weights does not list.
FALLBACK_WEIGHT = 1.0
# Seconds of work after which the ETA is shown, and that a step needs before
# its own rate is used instead of the whole run's.
MIN_DATA_SECONDS = 10.0
# The weight of the newest estimate in the smoothed ETA.
SMOOTHING = 0.3


def steps_of(kind: JobKind) -> tuple[str, ...]:
    """Return the steps a job of kind kind runs, in order."""
    if kind == "process":
        return PROCESS_STEPS
    if kind == "reprompt":
        return REPROMPT_STEPS
    if kind == "proedit":
        return PROEDIT_STEPS
    return RENDER_STEPS


def overall_progress(
    kind: JobKind,
    step: str,
    progress: float,
    weights: Mapping[str, float] | None = None,
) -> float:
    """Return the share, 0 to 1, of the job of kind kind that is done when it
    is at progress (0 to 1) of step step; 0 for a step it does not run.

    weights maps a step to its weight (default: Settings.step_weights).
    """
    steps = steps_of(kind)
    if step not in steps:
        return 0.0
    table = config.settings.step_weights if weights is None else weights
    weight = [max(table.get(name, FALLBACK_WEIGHT), 0.0) for name in steps]
    total = sum(weight)
    if total <= 0:
        return 0.0
    index = steps.index(step)
    done = sum(weight[:index]) + weight[index] * min(max(progress, 0.0), 1.0)
    return min(done / total, 1.0)


class EtaEstimator:
    """The smoothed seconds a job still needs, from its overall progress.

    update(step, overall) is called each time the job reports. The rate is
    the overall progress per second since the current step started, once the
    step has MIN_DATA_SECONDS of data, else since the first report. The
    estimate is remaining / rate; each new one is mixed into the previous one
    (which has aged by the time since): SMOOTHING * new + (1 - SMOOTHING) *
    previous.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._first: tuple[float, float] | None = None
        self._step: str | None = None
        self._step_start: tuple[float, float] = (0.0, 0.0)
        self._eta: float | None = None
        self._eta_at = 0.0

    def update(self, step: str, overall: float) -> float | None:
        """Record that the job is at overall (0 to 1) in step step and return
        the ETA in seconds; None while there is less than MIN_DATA_SECONDS
        of data, 0.0 when the job is done."""
        now = self._clock()
        if self._first is None:
            self._first = (now, overall)
        if step != self._step:
            self._step, self._step_start = step, (now, overall)
        if overall >= 1.0:
            return 0.0
        rate = self._rate(now, overall)
        if rate is None:
            return None
        raw = (1.0 - overall) / rate
        if self._eta is None:
            self._eta = raw
        else:
            aged = max(self._eta - (now - self._eta_at), 0.0)
            self._eta = SMOOTHING * raw + (1 - SMOOTHING) * aged
        self._eta_at = now
        return self._eta

    def _rate(self, now: float, overall: float) -> float | None:
        """Return the overall progress per second that the current step has
        measured, or the whole run's; None if there is not enough data."""
        assert self._first is not None
        for since, at_start in (self._step_start, self._first):
            seconds = now - since
            if seconds >= MIN_DATA_SECONDS and overall > at_start:
                return (overall - at_start) / seconds
        return None


class JobEtas:
    """The ETA estimators of the jobs this process runs, by job id."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._estimators: dict[int, EtaEstimator] = {}

    def update(self, job_id: int, step: str, overall: float) -> float | None:
        """Feed job job_id's overall progress to its estimator; its ETA."""
        estimator = self._estimators.setdefault(job_id, EtaEstimator(self._clock))
        return estimator.update(step, overall)

    def forget(self, job_id: int) -> None:
        """Drop the estimator of job job_id (it ended or stopped)."""
        self._estimators.pop(job_id, None)


etas = JobEtas()
