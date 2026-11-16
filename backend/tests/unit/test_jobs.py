"""Tests of the job worker: the lifecycle of process and render jobs, failures
and the reset of jobs that a stopped process left running."""

import time
from pathlib import Path

import pytest
from clipforge import jobs, process
from clipforge.db import ClipRow, JobRow, ProjectRow
from clipforge.models import JobStatus, ProcessingSettings
from clipforge.pipeline.reframe import crop_path
from clipforge.pipeline.step import StepError
from clipforge.worker_pool import WorkerPool
from fakes import FIXTURES, FakeLLMClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session, select

TRANSCRIPT = FIXTURES / "transcript.json"


def get_job(engine: Engine, job_id: int) -> JobRow:
    """Return the row of job job_id."""
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        assert job is not None
        return job


def project_status(engine: Engine, project_id: int) -> str:
    """Return the status of project project_id."""
    with Session(engine) as session:
        project = session.get(ProjectRow, project_id)
        assert project is not None
        return project.status


def add_process_job(engine: Engine, project_id: int, status: JobStatus) -> int:
    """Add a process job of project_id with status and return its id."""
    with Session(engine) as session:
        job = JobRow(
            project_id=project_id, kind="process", step="", log_path="", status=status
        )
        session.add(job)
        session.commit()
        assert job.id is not None
        return job.id


def wait_for_end(engine: Engine, job_id: int, seen: list[str]) -> None:
    """Record in seen each status that job job_id takes, until it is done or
    failed; fails the test after 120 s."""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status = get_job(engine, job_id).status
        if not seen or seen[-1] != status:
            seen.append(status)
        if status in ("done", "failed"):
            return
        time.sleep(0.02)
    pytest.fail(f"job {job_id} did not end; statuses: {seen}")


@pytest.mark.slow
@pytest.mark.usefixtures("yamnet_cfg", "face_cfg")
def test_the_worker_runs_a_process_job_and_then_a_render_job(
    engine: Engine, data_dir: Path, sample_mp4: Path
) -> None:
    worker = WorkerPool(
        engine, poll_interval=0.05, llm=FakeLLMClient(), transcript=TRANSCRIPT
    )
    worker.start()
    try:
        process_id = jobs.enqueue_process(
            engine, str(sample_mp4), ProcessingSettings(num_clips=1)
        )
        worker.wake()
        statuses: list[str] = []
        wait_for_end(engine, process_id, statuses)

        assert statuses == ["queued", "running", "done"]
        done = get_job(engine, process_id)
        assert (done.step, done.progress, done.error) == ("render", 1.0, None)
        with Session(engine) as session:
            (clip,) = session.exec(select(ClipRow)).all()
        assert clip.status == "rendered" and clip.output_path is not None
        assert project_status(engine, clip.project_id) == "done"
        assert "rendered 1 of 1 clips" in Path(done.log_path).read_text("utf-8")

        output = Path(clip.output_path)
        output.unlink()
        render_id = jobs.enqueue_render(engine, clip.id or 0)
        worker.wake()
        statuses = []
        wait_for_end(engine, render_id, statuses)
    finally:
        worker.stop(timeout=60)

    assert statuses[-1] == "done"
    render = get_job(engine, render_id)
    assert (render.kind, render.clip_id, render.project_id) == (
        "render",
        clip.id,
        clip.project_id,
    )
    assert (render.step, render.progress, render.error) == ("render", 1.0, None)
    assert output.is_file()
    assert render.log_path == str(data_dir / "work" / str(render_id) / "job.log")
    assert Path(render.log_path).is_file()


def test_a_failing_process_job_is_failed_and_the_next_job_runs(
    engine: Engine, tmp_path: Path
) -> None:
    missing = str(tmp_path / "missing.mp4")
    first = jobs.enqueue_process(engine, missing, ProcessingSettings())
    second = jobs.enqueue_process(engine, missing, ProcessingSettings())

    assert jobs.run_next(engine, llm=FakeLLMClient()) is True

    job = get_job(engine, first)
    assert (job.status, job.step) == ("failed", "ingest")
    assert job.error is not None and "source file not found" in job.error
    assert project_status(engine, job.project_id) == "failed"
    assert get_job(engine, second).status == "queued"

    assert jobs.run_next(engine, llm=FakeLLMClient()) is True
    assert get_job(engine, second).status == "failed"
    assert jobs.run_next(engine) is False


def test_a_render_job_of_a_clip_that_cannot_be_reframed_fails(
    engine: Engine, data_dir: Path
) -> None:
    project_id = add_project(engine)
    process_id = add_process_job(engine, project_id, "done")
    clip_id = add_clip(engine, project_id, "candidate", 50)
    assert not crop_path(data_dir / "work" / str(process_id), clip_id).exists()
    render_id = jobs.enqueue_render(engine, clip_id)

    assert jobs.run_next(engine) is True

    job = get_job(engine, render_id)
    assert (job.status, job.step) == ("failed", "render")
    assert job.error is not None and "meta.json" in job.error
    assert project_status(engine, project_id) == "queued"


def test_a_render_job_reframes_a_clip_without_a_crop_plan_first(
    engine: Engine, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = add_project(engine)
    process_id = add_process_job(engine, project_id, "done")
    clip_id = add_clip(engine, project_id, "candidate", 50)
    order: list[str] = []

    def ensure(engine: Engine, clip: int, work: Path) -> bool:
        order.append(f"reframe {clip} in {work.name}")
        return True

    def render(engine: Engine, clip: int, work: Path) -> None:
        order.append(f"render {clip}")
        raise StepError("stop here")

    monkeypatch.setattr(jobs, "ensure_crop_plan", ensure)
    monkeypatch.setattr(jobs, "render_clip_row", render)
    jobs.enqueue_render(engine, clip_id)

    assert jobs.run_next(engine) is True

    assert order == [f"reframe {clip_id} in {process_id}", f"render {clip_id}"]


def test_enqueue_render_adds_a_queued_job_for_the_clip(
    engine: Engine, data_dir: Path
) -> None:
    project_id = add_project(engine)
    add_process_job(engine, project_id, "done")
    latest = add_process_job(engine, project_id, "done")
    clip_id = add_clip(engine, project_id, "rendered", 50)

    job_id = jobs.enqueue_render(engine, clip_id)

    job = get_job(engine, job_id)
    assert (job.kind, job.clip_id, job.project_id) == ("render", clip_id, project_id)
    assert (job.step, job.progress, job.status, job.error) == ("", 0.0, "queued", None)
    assert job.log_path == str(data_dir / "work" / str(job_id) / "job.log")
    assert job_id != latest


def test_enqueue_render_needs_a_clip_with_a_process_job(engine: Engine) -> None:
    with pytest.raises(StepError, match="clip 7 not found"):
        jobs.enqueue_render(engine, 7)
    project_id = add_project(engine)
    clip_id = add_clip(engine, project_id, "candidate", 50)
    with pytest.raises(StepError, match=f"project {project_id} has no process job"):
        jobs.enqueue_render(engine, clip_id)


def test_reset_stale_jobs_queues_the_running_jobs_again(engine: Engine) -> None:
    job_id = process.create_job(engine, "/videos/a.mp4", ProcessingSettings())
    other_id = process.create_job(engine, "/videos/b.mp4", ProcessingSettings())
    done_id = process.create_job(engine, "/videos/c.mp4", ProcessingSettings())
    with Session(engine) as session:
        for number, status in ((job_id, "running"), (done_id, "done")):
            job = session.get(JobRow, number)
            assert job is not None
            job.status, job.step, job.progress = status, "curate", 0.4
            project = session.get(ProjectRow, job.project_id)
            assert project is not None
            project.status = status
        session.commit()

    assert jobs.reset_stale_jobs(engine) == [job_id]

    stale = get_job(engine, job_id)
    assert (stale.status, stale.step, stale.progress) == ("queued", "", 0.0)
    assert project_status(engine, stale.project_id) == "queued"
    assert get_job(engine, other_id).status == "queued"
    done = get_job(engine, done_id)
    assert (done.status, done.step, done.progress) == ("done", "curate", 0.4)
    assert project_status(engine, done.project_id) == "done"
    assert jobs.reset_stale_jobs(engine) == []


def test_a_restarted_process_job_replaces_the_clips_of_its_first_run(
    engine: Engine, tmp_path: Path
) -> None:
    job_id = jobs.enqueue_process(
        engine, str(tmp_path / "missing.mp4"), ProcessingSettings()
    )
    project_id = get_job(engine, job_id).project_id
    add_clip(engine, project_id, "candidate", 50)
    with Session(engine) as session:
        session.get(JobRow, job_id).status = "running"  # type: ignore[union-attr]
        session.commit()

    worker = WorkerPool(engine, poll_interval=0.01, llm=FakeLLMClient())
    worker.start()
    try:
        statuses: list[str] = []
        wait_for_end(engine, job_id, statuses)
    finally:
        worker.stop(timeout=30)

    assert statuses[-1] == "failed"
    with Session(engine) as session:
        assert session.exec(select(ClipRow)).all() == []


def test_the_worker_starts_once_and_stops(engine: Engine) -> None:
    worker = WorkerPool(engine, poll_interval=0.01)
    worker.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            worker.start()
    finally:
        worker.stop(timeout=10)
    worker.start()
    worker.stop(timeout=10)
