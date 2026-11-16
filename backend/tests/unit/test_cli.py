"""Tests of the clipforge command line: `clipforge step` and the arguments and
exit codes of `clipforge run` (renders: tests/pipeline/test_run_minimal.py)."""

import os
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from clipforge import cli, process
from clipforge.db import JobRow, ProjectRow, init_db
from clipforge.models import ProcessingSettings, SourceMeta
from clipforge.pipeline.step import StepSettings
from clipforge.testmode import ENV_VAR
from fakes import FIXTURES
from sqlalchemy import Engine
from sqlmodel import Session, select


def add_job(engine: Engine, source_path: str, source_url: str | None = None) -> int:
    """Add a project with this source and a process job for it; return the job id."""
    settings = ProcessingSettings(timeframe_start=5.0, timeframe_end=30.0)
    with Session(engine) as session:
        project = ProjectRow(
            source_url=source_url,
            source_path=source_path,
            title="",
            duration=0.0,
            thumbnail_path="",
            settings=settings,
        )
        session.add(project)
        session.commit()
        assert project.id is not None
        job = JobRow(project_id=project.id, kind="process", step="", log_path="job.log")
        session.add(job)
        session.commit()
        assert job.id is not None
        return job.id


def get_job(engine: Engine, job_id: int) -> JobRow:
    """Load job job_id from the database."""
    with Session(engine) as session:
        job = session.get(JobRow, job_id)
        assert job is not None
        return job


def test_step_ingest_runs_the_step_for_the_job(
    engine: Engine, data_dir: Path, sample_mp4: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    job_id = add_job(engine, str(sample_mp4))

    assert cli.main(["step", "ingest", str(job_id)]) == 0

    meta_path = data_dir / "work" / str(job_id) / "meta.json"
    assert capsys.readouterr().out == f"{meta_path}\n"
    meta = SourceMeta.model_validate_json(meta_path.read_text())
    assert (meta.timeframe_start, meta.timeframe_end) == (5.0, 30.0)
    job = get_job(engine, job_id)
    assert (job.step, job.progress, job.status, job.error) == (
        "ingest",
        1.0,
        "queued",
        None,
    )


def test_job_records_the_step_and_its_rounded_progress(
    engine: Engine, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://www.youtube.com/watch?v=clipforge01"
    job_id = add_job(engine, "", source_url=url)
    seen: list[tuple[str, float]] = []

    def step(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
        assert (job_dir, settings.source, force) == (
            data_dir / "work" / str(job_id),
            url,
            True,
        )
        assert settings.processing.timeframe_end == 30.0
        for fraction in (0.0, 0.123, 0.1249, 0.5):
            settings.report_progress(fraction)
            job = get_job(engine, job_id)
            seen.append((job.step, job.progress))
        return job_dir / "out.json"

    monkeypatch.setattr(process, "load_step", lambda name: step)

    assert cli.main(["step", "ingest", str(job_id), "--force"]) == 0
    assert seen == [
        ("ingest", 0.0),
        ("ingest", 0.12),
        ("ingest", 0.12),
        ("ingest", 0.5),
    ]
    assert get_job(engine, job_id).progress == 1.0


def test_step_skips_finished_work_unless_forced(
    engine: Engine, data_dir: Path, sample_mp4: Path
) -> None:
    job_id = add_job(engine, str(sample_mp4))
    assert cli.main(["step", "ingest", str(job_id)]) == 0
    outputs = sorted((data_dir / "work" / str(job_id)).iterdir())
    old = 1_000_000_000.0
    for path in outputs:
        os.utime(path, (old, old))

    assert cli.main(["step", "ingest", str(job_id)]) == 0
    assert [path.stat().st_mtime for path in outputs] == [old] * len(outputs)
    assert get_job(engine, job_id).progress == 1.0

    assert cli.main(["step", "ingest", str(job_id), "--force"]) == 0
    assert all(path.stat().st_mtime > old for path in outputs)


def test_unknown_job_is_an_error(
    engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["step", "ingest", "999"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "clipforge: error: job 999 not found" in captured.err.splitlines()


def test_failed_step_is_an_error_and_the_job_keeps_its_status(
    engine: Engine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.mp4"
    job_id = add_job(engine, str(missing))

    assert cli.main(["step", "ingest", str(job_id)]) == 1

    error = f"clipforge: error: source file not found: {missing}"
    assert error in capsys.readouterr().err.splitlines()
    job = get_job(engine, job_id)
    assert (job.step, job.progress, job.status) == ("ingest", 0.0, "queued")


@pytest.mark.parametrize(
    ("argv", "error"),
    [
        ([], "the following arguments are required: command"),
        (["step"], "the following arguments are required: name, job_id"),
        (["step", "bogus", "1"], "argument name: invalid choice: 'bogus'"),
        (["step", "ingest", "abc"], "argument job_id: invalid int value: 'abc'"),
        (["run"], "the following arguments are required: source"),
        (["run", "a.mp4", "--genre", "drama"], "argument --genre: invalid choice"),
        (["run", "a.mp4", "--aspect", "1:9"], "argument --aspect: aspect 1:9 is more"),
        (
            ["run", "a.mp4", "--num-clips", "0"],
            "argument --num-clips: input should be greater than or equal to 1",
        ),
        (
            ["run", "a.mp4", "--num-clips", "31"],
            "argument --num-clips: input should be less than or equal to 30",
        ),
        (["run", "a.mp4", "--num-clips", "two"], "argument --num-clips: input"),
        (
            ["run", "a.mp4", "--fixtures-dir", str(FIXTURES)],
            "--fixtures-dir needs CLIPFORGE_TEST_MODE=1",
        ),
    ],
)
def test_bad_arguments_exit_with_status_2(
    data_dir: Path,
    argv: list[str],
    error: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv)
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith("usage: clipforge")
    assert f"error: {error}" in err
    assert not data_dir.exists()


def test_test_mode_without_a_fixtures_dir_exits_with_status_2(
    data_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, "1")
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["run", "a.mp4"])
    assert exit_info.value.code == 2
    error = "clipforge: error: CLIPFORGE_TEST_MODE=1 needs --fixtures-dir"
    assert error in capsys.readouterr().err.splitlines()
    assert not data_dir.exists()


def test_run_with_a_missing_source_fails_its_job(
    engine: Engine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.mp4"

    assert cli.main(["run", str(missing)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    error = f"clipforge: error: source file not found: {missing}"
    assert error in captured.err.splitlines()
    job = get_job(engine, 1)
    assert (job.kind, job.step, job.status) == ("process", "ingest", "failed")


@pytest.mark.slow
@pytest.mark.usefixtures("yamnet_cfg")
def test_run_in_test_mode_exits_0_when_the_video_has_no_clips(
    engine: Engine,
    sample_mp4: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = tmp_path / "recorded"
    recorded.mkdir()
    (recorded / "transcript.json").write_bytes(
        (FIXTURES / "transcript.json").read_bytes()
    )
    (recorded / "llm_response.json").write_text('{"clips": []}', encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, "1")

    argv = [
        "run",
        str(sample_mp4),
        "--genre",
        "comedy",
        "--fixtures-dir",
        str(recorded),
    ]
    assert cli.main(argv) == 0

    assert capsys.readouterr().out == ""
    job = get_job(engine, 1)
    assert (job.status, job.step) == ("done", "render")
    with Session(engine) as session:
        project = session.exec(select(ProjectRow)).one()
    assert (project.settings.genre, project.status) == ("comedy", "done")


def test_clipforge_command_ingests_a_job(sample_mp4: Path, tmp_path: Path) -> None:
    (script,) = entry_points(group="console_scripts", name="clipforge")
    assert script.load() is cli.main
    data = tmp_path / "data"
    engine = init_db(data)
    job_id = add_job(engine, str(sample_mp4))
    engine.dispose()

    command = [
        Path(sys.executable).with_name("clipforge"),
        "step",
        "ingest",
        str(job_id),
    ]
    env = {**os.environ, "DATA_DIR": str(data)}
    result = subprocess.run(
        command, env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{data / 'work' / str(job_id) / 'meta.json'}\n"
    assert "INFO clipforge.pipeline.ingest: ingested 'ClipForge" in result.stderr
