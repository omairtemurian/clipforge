"""Tests of the process job: creating it and the job and project statuses."""

from pathlib import Path

import pytest
from clipforge import process
from clipforge.db import ClipRow, JobRow, ProjectRow
from clipforge.models import ProcessingSettings, SourceMeta
from clipforge.pipeline.step import StepError
from fakes import FIXTURES, FakeLLMClient
from sqlalchemy import Engine
from sqlmodel import Session, select


def load(engine: Engine, job_id: int) -> tuple[JobRow, ProjectRow]:
    """Return the rows of job job_id and its project."""
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        assert job is not None
        project = session.get(ProjectRow, job.project_id)
        assert project is not None
        return job, project


def test_create_job_adds_a_project_and_a_queued_process_job(
    engine: Engine, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = ProcessingSettings(genre="comedy", aspect="1:1", num_clips=4)

    job_id = process.create_job(engine, "videos/set.mp4", settings)

    job, project = load(engine, job_id)
    assert (job.kind, job.step, job.progress, job.status, job.error) == (
        "process",
        "",
        0.0,
        "queued",
        None,
    )
    assert job.log_path == str(data_dir / "work" / str(job_id) / "job.log")
    assert (project.source_url, project.source_path) == (
        None,
        str(tmp_path / "videos" / "set.mp4"),
    )
    assert (project.title, project.duration, project.thumbnail_path) == ("", 0.0, "")
    assert (project.settings, project.status) == (settings, "queued")


def test_create_job_keeps_a_url_as_the_source_url(engine: Engine) -> None:
    url = "https://www.youtube.com/watch?v=clipforge01"

    job_id = process.create_job(engine, url, ProcessingSettings())

    _, project = load(engine, job_id)
    assert (project.source_url, project.source_path) == (url, "")


def test_a_failing_step_fails_the_job_and_its_project(
    engine: Engine, tmp_path: Path
) -> None:
    missing = tmp_path / "missing.mp4"
    job_id = process.create_job(engine, str(missing), ProcessingSettings())

    with pytest.raises(StepError, match="source file not found") as error:
        process.run_process_job(engine, job_id, llm=FakeLLMClient())

    job, project = load(engine, job_id)
    assert (job.step, job.status, job.error) == ("ingest", "failed", str(error.value))
    assert project.status == "failed"


@pytest.mark.slow
@pytest.mark.usefixtures("yamnet_cfg")
def test_a_video_without_clips_is_done_with_no_clips(
    engine: Engine, data_dir: Path, sample_mp4: Path, caplog: pytest.LogCaptureFixture
) -> None:
    job_id = process.create_job(engine, str(sample_mp4), ProcessingSettings())
    no_clips = FakeLLMClient('{"clips": []}', repeat_last=True)

    clips = process.run_process_job(
        engine, job_id, llm=no_clips, transcript=FIXTURES / "transcript.json"
    )

    assert clips == []
    job, project = load(engine, job_id)
    assert (job.step, job.progress, job.status) == ("render", 1.0, "done")
    assert (project.status, project.title, project.duration) == (
        "done",
        "ClipForge sample fixture",
        60.0,
    )
    work = data_dir / "work" / str(job_id)
    assert project.thumbnail_path == str(work / "thumb.jpg")
    assert f"job {job_id} found no clips in the video" in caplog.messages
    assert "found no clips" in (work / "job.log").read_text(encoding="utf-8")
    with Session(engine) as session:
        assert session.exec(select(ClipRow)).all() == []


def test_running_a_missing_job_is_an_error(engine: Engine) -> None:
    with pytest.raises(StepError, match="job 99 not found"):
        process.run_process_job(engine, 99)


def test_ingest_title_does_not_replace_a_title_the_owner_gave(
    engine: Engine, data_dir: Path
) -> None:
    job_id = process.create_job(engine, "/videos/talk.mp4", ProcessingSettings())
    work = data_dir / "work" / str(job_id)
    work.mkdir(parents=True)
    meta = SourceMeta(
        title="talk.mp4 title",
        duration=42.0,
        width=1920,
        height=1080,
        fps=30.0,
        timeframe_start=0.0,
        timeframe_end=42.0,
    )
    (work / "meta.json").write_text(meta.model_dump_json(), encoding="utf-8")
    with Session(engine) as session:
        _, project = load(engine, job_id)
        project.title = "My rename"
        session.add(project)
        session.commit()

    process._describe_project(engine, job_id, work)

    _, project = load(engine, job_id)
    assert (project.title, project.duration) == ("My rename", 42.0)
