"""Tests of resumable jobs (SPEC-v2 2.2): the stage markers, a job that
resumes after a killed worker, attempts and poison jobs."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from builders import source_meta
from clipforge import config, jobs, process
from clipforge.db import ClipRow, JobRow, ProjectRow
from clipforge.models import ProcessingSettings, ScoredList
from clipforge.pipeline.step import (
    META,
    SNAPPED,
    SOURCE,
    STEP_NAMES,
    Step,
    StepSettings,
    done_steps,
    job_dir,
    mark_done,
    marker_path,
    step_done,
    write_json,
)
from clipforge.process_clips import CLIPS_STAGE, REFRAME_STEP
from fakes import FIXTURES, FakeLLMClient
from seed import add_clip
from sqlalchemy import Engine
from sqlmodel import Session, select

TRANSCRIPT = FIXTURES / "transcript.json"
WORKER = Path(__file__).resolve().parents[1] / "resume_worker.py"


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


def record_steps(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make process.load_step record the name of each step it loads (the
    real steps still run) and return the list it records into."""
    loaded: list[str] = []
    real_load_step = process.load_step

    def load_step(name: str) -> Step:
        loaded.append(name)
        return real_load_step(name)

    monkeypatch.setattr(process, "load_step", load_step)
    return loaded


def finished_work(job_id: int, stages: tuple[str, ...]) -> Path:
    """Return the work directory of job job_id with the outputs that the
    clip stages read (meta.json, an empty snapped.json) and the stages
    marked done."""
    work = job_dir(job_id)
    work.mkdir(parents=True)
    write_json(work / META, source_meta())
    write_json(work / SNAPPED, ScoredList(clips=[]))
    for name in stages:
        mark_done(work, name)
    return work


def test_mark_done_writes_the_marker_of_a_stage(tmp_path: Path) -> None:
    assert not step_done(tmp_path, "ingest") and done_steps(tmp_path) == []

    mark_done(tmp_path, "transcribe")
    mark_done(tmp_path, "ingest")

    assert marker_path(tmp_path, "ingest") == tmp_path / "steps" / "ingest.done"
    assert step_done(tmp_path, "ingest") and not step_done(tmp_path, "signals")
    assert done_steps(tmp_path) == ["ingest", "transcribe"]
    assert not list((tmp_path / "steps").glob("*.tmp"))


def test_run_step_marks_a_step_done_only_when_it_finishes(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job_id = process.create_job(engine, str(tmp_path / "a.mp4"), ProcessingSettings())
    work = job_dir(job_id)

    def fails(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
        raise RuntimeError("stopped")

    def writes(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "out.txt").write_text("out")
        return job_dir / "out.txt"

    monkeypatch.setattr(process, "load_step", lambda name: fails)
    with pytest.raises(RuntimeError, match="stopped"):
        process.run_step(engine, "ingest", job_id)
    assert not step_done(work, "ingest")

    monkeypatch.setattr(process, "load_step", lambda name: writes)
    process.run_step(engine, "ingest", job_id)
    assert done_steps(work) == ["ingest"]


def test_a_job_skips_the_steps_and_stages_that_it_finished(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job_id = process.create_job(
        engine, str(tmp_path / "gone.mp4"), ProcessingSettings()
    )
    project_id = get_job(engine, job_id).project_id
    finished_work(job_id, (*STEP_NAMES, CLIPS_STAGE, REFRAME_STEP))
    clip_id = add_clip(engine, project_id, "rendered", 70)
    with Session(engine) as session:
        clip = session.get(ClipRow, clip_id)
        assert clip is not None and clip.output_path is not None
        video = Path(clip.output_path)
    video.parent.mkdir(parents=True)
    video.write_bytes(b"rendered before the restart")
    loaded = record_steps(monkeypatch)

    clips = process.run_process_job(engine, job_id, llm=FakeLLMClient())

    assert loaded == []
    assert [(clip.id, clip.status) for clip in clips] == [(clip_id, "rendered")]
    assert video.read_bytes() == b"rendered before the restart"
    job = get_job(engine, job_id)
    assert (job.status, job.step, job.progress) == ("done", "render", 1.0)
    assert project_status(engine, project_id) == "done"


def test_a_job_without_the_clips_marker_deletes_its_clips_and_saves_them(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job_id = process.create_job(
        engine, str(tmp_path / "gone.mp4"), ProcessingSettings()
    )
    project_id = get_job(engine, job_id).project_id
    work = finished_work(job_id, STEP_NAMES)
    add_clip(engine, project_id, "candidate", 40)
    loaded = record_steps(monkeypatch)

    assert process.run_process_job(engine, job_id, llm=FakeLLMClient()) == []

    assert loaded == []
    with Session(engine) as session:
        assert session.exec(select(ClipRow)).all() == []
    assert done_steps(work) == sorted([*STEP_NAMES, CLIPS_STAGE, REFRAME_STEP])


def test_claim_next_counts_the_attempts(engine: Engine, tmp_path: Path) -> None:
    job_id = jobs.enqueue_process(engine, str(tmp_path / "a.mp4"), ProcessingSettings())
    assert get_job(engine, job_id).attempts == 0

    for attempt in (1, 2):
        claimed = jobs.claim_next(engine)
        assert claimed is not None and claimed.id == job_id
        assert get_job(engine, job_id).attempts == attempt
        assert jobs.reset_stale_jobs(engine) == [job_id]
        assert get_job(engine, job_id).to_model().attempts == attempt


def test_a_poison_job_fails_after_the_most_attempts(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        config, "settings", config.settings.model_copy(update={"job_max_attempts": 2})
    )
    job_id = jobs.enqueue_process(engine, str(tmp_path / "a.mp4"), ProcessingSettings())
    project_id = get_job(engine, job_id).project_id
    rendering = add_clip(engine, project_id, "rendering", 50)

    assert jobs.claim_next(engine) is not None
    assert jobs.reset_stale_jobs(engine) == [job_id]
    assert jobs.claim_next(engine) is not None
    assert jobs.reset_stale_jobs(engine) == []

    job = get_job(engine, job_id)
    assert (job.status, job.attempts) == ("failed", 2)
    assert job.error is not None and "2 times" in job.error
    assert project_status(engine, project_id) == "failed"
    with Session(engine) as session:
        clip = session.get(ClipRow, rendering)
        assert clip is not None and (clip.status, clip.output_path) == ("failed", None)
    assert jobs.claim_next(engine) is None


def test_a_poison_render_job_fails_only_its_clip(
    engine: Engine, tmp_path: Path
) -> None:
    process_id = jobs.enqueue_process(
        engine, str(tmp_path / "a.mp4"), ProcessingSettings()
    )
    project_id = get_job(engine, process_id).project_id
    with Session(engine) as session:
        session.get(JobRow, process_id).status = "done"  # type: ignore[union-attr]
        session.commit()
    mine = add_clip(engine, project_id, "rendering", 50)
    other = add_clip(engine, project_id, "rendering", 40)
    render_id = jobs.enqueue_render(engine, mine)
    assert jobs.claim_next(engine) is not None

    assert jobs.reset_stale_jobs(engine, max_attempts=1) == []

    assert get_job(engine, render_id).status == "failed"
    assert project_status(engine, project_id) == "queued"
    with Session(engine) as session:
        statuses = {c.id: c.status for c in session.exec(select(ClipRow)).all()}
    assert statuses == {mine: "failed", other: "rendering"}


def wait_for(path: Path, worker: subprocess.Popen[bytes]) -> None:
    """Wait until path exists; fails the test if worker ends or after 120 s."""
    deadline = time.monotonic() + 120
    while not path.exists():
        if worker.poll() is not None:
            pytest.fail(f"the worker ended with exit code {worker.returncode}")
        if time.monotonic() > deadline:
            pytest.fail(f"the worker did not write {path} in 120 s")
        time.sleep(0.05)


@pytest.mark.slow
@pytest.mark.usefixtures("yamnet_cfg", "face_cfg")
def test_a_job_of_a_killed_worker_resumes_after_its_last_finished_step(
    engine: Engine,
    data_dir: Path,
    sample_mp4: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    job_id = jobs.enqueue_process(
        engine, str(sample_mp4), ProcessingSettings(num_clips=1)
    )
    reached = tmp_path / "reached"
    models = str(config.settings.models_dir)
    env = os.environ | {"DATA_DIR": str(data_dir), "MODELS_DIR": models}
    command = [sys.executable, str(WORKER), "signals", str(reached), str(TRANSCRIPT)]
    worker = subprocess.Popen(command, cwd=tmp_path, env=env)
    try:
        wait_for(reached, worker)
    finally:
        worker.kill()
        worker.wait(30)

    work = job_dir(job_id)
    killed = get_job(engine, job_id)
    assert (killed.status, killed.step, killed.attempts) == ("running", "signals", 1)
    assert done_steps(work) == ["ingest", "transcribe"]
    ingested = {name: (work / name).stat().st_mtime_ns for name in (SOURCE, META)}

    assert jobs.reset_stale_jobs(engine) == [job_id]
    loaded = record_steps(monkeypatch)
    assert jobs.run_next(engine, llm=FakeLLMClient(), transcript=TRANSCRIPT)

    assert loaded == ["signals", "visuals", "enrich", "curate", "score", "snap"]
    assert {name: (work / name).stat().st_mtime_ns for name in ingested} == ingested
    done = get_job(engine, job_id)
    assert (done.status, done.step, done.attempts, done.error) == (
        "done",
        "render",
        2,
        None,
    )
    with Session(engine) as session:
        (clip,) = session.exec(select(ClipRow)).all()
    assert clip.status == "rendered" and Path(clip.output_path or "").is_file()
    assert "resumes; finished: ['ingest', 'transcribe']" in Path(
        done.log_path
    ).read_text("utf-8")
