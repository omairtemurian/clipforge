"""Tests of the overall progress and ETA of a job (job_progress, steering
2026-11-02): weighted steps and the smoothed ETA on a fake clock."""

import pytest
from clipforge import job_progress
from clipforge.db import JobRow, ProjectRow
from clipforge.job_progress import EtaEstimator, JobEtas, overall_progress
from clipforge.job_rows import record_progress, set_step
from fake_clock import FakeClock
from seed import add_job, add_project
from sqlalchemy import Engine
from sqlmodel import Session

# Weights that sum to 100 (the defaults of Settings.step_weights).
WEIGHTS = {
    "ingest": 10,
    "transcribe": 25,
    "signals": 5,
    "visuals": 3,
    "enrich": 1,
    "curate": 10,
    "score": 1,
    "snap": 1,
    "reframe": 10,
    "render": 34,
}


@pytest.mark.parametrize(
    ("step", "progress", "expected"),
    [
        ("ingest", 0.0, 0.0),
        ("ingest", 0.5, 0.05),
        ("transcribe", 0.0, 0.10),
        ("transcribe", 0.4, 0.20),
        ("curate", 1.0, 0.54),
        ("reframe", 0.5, 0.61),
        ("render", 0.0, 0.66),
        ("render", 0.5, 0.83),
        ("render", 1.0, 1.0),
        ("render", 7.0, 1.0),
        ("unknown", 0.5, 0.0),
    ],
)
def test_a_process_job_weighs_each_step_by_its_share(
    step: str, progress: float, expected: float
) -> None:
    assert overall_progress("process", step, progress, WEIGHTS) == pytest.approx(
        expected
    )


def test_a_reprompt_job_counts_only_its_own_steps() -> None:
    # curate 10 of (3 + 10 + 1 + 1 + 10 + 34) = 59
    assert overall_progress("reprompt", "curate", 1.0, WEIGHTS) == pytest.approx(
        13 / 59
    )
    assert overall_progress("reprompt", "ingest", 0.5, WEIGHTS) == 0.0


def test_a_render_job_is_all_render() -> None:
    assert overall_progress("render", "render", 0.25, WEIGHTS) == 0.25


def test_the_default_weights_are_the_settings() -> None:
    assert overall_progress("process", "transcribe", 0.4) == pytest.approx(0.2)


def test_a_step_without_a_weight_counts_one() -> None:
    assert overall_progress("render", "render", 0.5, {}) == 0.5
    assert overall_progress("process", "ingest", 1.0, {"ingest": 1}) == pytest.approx(
        1 / 10
    )


def test_the_eta_is_unknown_for_the_first_ten_seconds() -> None:
    clock = FakeClock(1000.0)
    eta = EtaEstimator(clock)
    assert eta.update("ingest", 0.0) is None
    clock.now = 1009.9
    assert eta.update("ingest", 0.5) is None


def test_the_eta_is_remaining_work_over_the_measured_rate() -> None:
    clock = FakeClock(1000.0)
    eta = EtaEstimator(clock)
    eta.update("ingest", 0.0)
    clock.now = 1010.0
    assert eta.update("ingest", 0.1) == pytest.approx(90.0)


def test_the_eta_is_smoothed_and_ages_between_reports() -> None:
    clock = FakeClock(1000.0)
    eta = EtaEstimator(clock)
    eta.update("ingest", 0.0)
    clock.now = 1010.0
    eta.update("ingest", 0.1)  # 90
    clock.now = 1020.0
    # A steady rate: the aged 80 and the new 80.
    assert eta.update("ingest", 0.2) == pytest.approx(80.0)
    clock.now = 1030.0
    # No progress: new 0.8 / (0.2 / 30) = 120, aged 70: 0.3 * 120 + 0.7 * 70.
    assert eta.update("ingest", 0.2) == pytest.approx(85.0)


def test_a_new_step_starts_from_the_rate_of_the_whole_run() -> None:
    clock = FakeClock(1000.0)
    eta = EtaEstimator(clock)
    eta.update("ingest", 0.0)
    clock.now = 1010.0
    eta.update("ingest", 0.1)
    clock.now = 1020.0
    eta.update("ingest", 0.2)
    clock.now = 1030.0
    eta.update("ingest", 0.2)  # 85
    clock.now = 1040.0
    # The step has no data yet: 0.3 / 40 s = 0.0075 / s gives 93.33; aged 75.
    assert eta.update("transcribe", 0.3) == pytest.approx(0.3 * 93.3333333 + 52.5)
    clock.now = 1055.0
    # 15 s of the step: 0.15 / 15 = 0.01 / s gives 55; aged 65.5.
    assert eta.update("transcribe", 0.45) == pytest.approx(0.3 * 55 + 0.7 * 65.5)


def test_a_job_that_resumes_counts_only_the_work_it_does() -> None:
    clock = FakeClock(0.0)
    eta = EtaEstimator(clock)
    eta.update("curate", 0.5)  # finished steps before it do not count
    clock.now = 20.0
    assert eta.update("curate", 0.6) == pytest.approx(0.4 / (0.1 / 20))


def test_a_finished_job_needs_no_time() -> None:
    clock = FakeClock(0.0)
    eta = EtaEstimator(clock)
    assert eta.update("render", 1.0) == 0.0


def test_each_job_has_its_own_estimator() -> None:
    clock = FakeClock(0.0)
    etas = JobEtas(clock)
    etas.update(1, "ingest", 0.0)
    etas.update(2, "ingest", 0.0)
    clock.now = 10.0
    assert etas.update(1, "ingest", 0.5) == pytest.approx(10.0)
    assert etas.update(2, "ingest", 0.25) == pytest.approx(30.0)
    etas.forget(1)
    assert etas.update(1, "ingest", 0.5) is None


def test_the_job_and_its_project_get_the_progress_and_eta(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock(0.0)
    monkeypatch.setattr(job_progress, "etas", JobEtas(clock))
    project_id = add_project(engine)
    job_id = add_job(engine, project_id, "running")

    set_step(engine, job_id, "transcribe")
    clock.now = 10.0
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        assert job is not None
        record_progress(session, job, "transcribe", 0.4)
        session.commit()

    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        project = session.get(ProjectRow, project_id)
        assert job is not None and project is not None
        assert (job.step, job.progress) == ("transcribe", 0.4)
        assert job.overall_progress == pytest.approx(0.2)
        assert project.overall_progress == pytest.approx(0.2)
        # 0.1 -> 0.2 in 10 s: 0.8 left at 0.01 / s.
        assert job.eta_seconds == project.eta_seconds == pytest.approx(80.0)
