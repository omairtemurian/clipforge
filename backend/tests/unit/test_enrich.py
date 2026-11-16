"""Tests of the enrich step (SPEC 6.4), which writes the transcript lines that
the LLM reads, with signal markers, to enriched.txt (the lines themselves:
test_enrich_lines.py)."""

import logging
from collections.abc import Sequence
from pathlib import Path

import pytest
from builders import cut, event, segment
from clipforge import cli, process
from clipforge.models import (
    ProcessingSettings,
    Segment,
    SignalEvent,
    SignalList,
    SourceMeta,
    Transcript,
)
from clipforge.pipeline import enrich
from clipforge.pipeline.step import (
    ENRICHED,
    META,
    SIGNALS,
    STEP_NAMES,
    TRANSCRIPT,
    StepError,
    StepSettings,
    load_step,
    write_json,
)
from sqlalchemy import Engine

THREE = [
    segment(0, "Hi everyone.", [0.52, 0.79], 1.41),
    segment(1, "So, I tried yoga.", [1.53, 1.86, 2.0, 2.38], 2.91),
    segment(
        2,
        "The teacher says, listen to your body.",
        [5.12, 5.3, 5.7, 6.3, 6.64, 6.76, 6.95],
        7.43,
    ),
]
LAUGH = event("laugh", 2.95, 5.05, 0.85)
# Silences and energy peaks get no marker.
UNMARKED = [event("silence", 2.91, 5.12), event("energy_peak", 3.0, 4.8, 0.6)]
THREE_ENRICHED = (
    "[00:00.5-00:01.4] S0: Hi everyone.\n"
    "[00:01.5-00:02.9] S0: So, I tried yoga. [LAUGH 2.1s 0.85]\n"
    "[00:05.1-00:07.4] S0: The teacher says, [SCENE CUT] listen to your body.\n"
)


def write_job(
    job_dir: Path,
    segments: Sequence[Segment],
    events: Sequence[SignalEvent],
    *,
    start: float = 0.0,
    end: float = 60.0,
) -> Path:
    """Write the meta.json, transcript.json and signals.json of a 60 s video."""
    meta = SourceMeta(
        title="sample",
        duration=60.0,
        width=1280,
        height=720,
        fps=30.0,
        timeframe_start=start,
        timeframe_end=end,
    )
    write_json(job_dir / META, meta)
    transcript = Transcript(language="en", duration=60.0, segments=list(segments))
    write_json(job_dir / TRANSCRIPT, transcript)
    write_json(job_dir / SIGNALS, SignalList(list(events)))
    return job_dir


def test_three_segments_with_a_laugh_and_a_scene_cut(tmp_path: Path) -> None:
    job = write_job(tmp_path, THREE, [LAUGH, *UNMARKED, cut(6.1)])
    progress: list[float] = []
    settings = StepSettings(source="video.mp4", on_progress=progress.append)

    assert enrich.run(job, settings) == job / ENRICHED

    assert (job / ENRICHED).read_text(encoding="utf-8") == THREE_ENRICHED
    assert progress == [1.0]
    assert sorted(path.name for path in job.iterdir()) == sorted(
        [ENRICHED, META, SIGNALS, TRANSCRIPT]
    )


def test_only_the_timeframe_is_enriched(tmp_path: Path) -> None:
    events = [event("applause", 1.0, 1.5), LAUGH, cut(6.1)]
    job = write_job(tmp_path, THREE, events, start=1.5, end=6.0)

    enrich.run(job, StepSettings(source="video.mp4"))

    assert (job / ENRICHED).read_text(encoding="utf-8") == (
        "[00:01.5-00:02.9] S0: So, I tried yoga. [LAUGH 2.1s 0.85]\n"
        "[00:05.1-00:07.4] S0: The teacher says, listen to your body.\n"
    )


def test_finished_work_is_skipped_unless_forced(tmp_path: Path) -> None:
    job = write_job(tmp_path, THREE, [LAUGH, cut(6.1)])
    (job / ENRICHED).write_text("old\n", encoding="utf-8")
    progress: list[float] = []
    settings = StepSettings(source="video.mp4", on_progress=progress.append)

    assert enrich.run(job, settings) == job / ENRICHED
    assert (job / ENRICHED).read_text(encoding="utf-8") == "old\n"
    assert progress == [1.0]

    enrich.run(job, settings, force=True)
    assert (job / ENRICHED).read_text(encoding="utf-8") == THREE_ENRICHED


def test_a_timeframe_without_speech_gives_an_empty_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    job = write_job(tmp_path, THREE, [LAUGH], start=30.0, end=60.0)

    with caplog.at_level(logging.WARNING, logger="clipforge.pipeline.enrich"):
        enrich.run(job, StepSettings(source="video.mp4"))

    assert (job / ENRICHED).read_text(encoding="utf-8") == ""
    assert "no speech in 30.0s-60.0s" in caplog.text


@pytest.mark.parametrize(
    ("missing", "step"),
    [(META, "ingest"), (TRANSCRIPT, "transcribe"), (SIGNALS, "signals")],
)
def test_enrich_needs_the_earlier_steps(
    tmp_path: Path, missing: str, step: str
) -> None:
    job = write_job(tmp_path, THREE, [LAUGH])
    (job / ENRICHED).write_text("old\n", encoding="utf-8")
    (job / missing).unlink()

    with pytest.raises(StepError, match=f"{missing} not found; run the {step} step"):
        enrich.run(job, StepSettings(source="video.mp4"), force=True)
    assert not (job / ENRICHED).exists()


def test_enrich_is_the_step_between_visuals_and_curate() -> None:
    assert STEP_NAMES.index("visuals") == STEP_NAMES.index("signals") + 1
    assert STEP_NAMES.index("enrich") == STEP_NAMES.index("visuals") + 1
    assert STEP_NAMES.index("curate") == STEP_NAMES.index("enrich") + 1
    assert load_step("enrich") is enrich.run


def test_step_command_runs_enrich_for_a_job(
    engine: Engine, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    job_id = process.create_job(engine, "video.mp4", ProcessingSettings())
    work = data_dir / "work" / str(job_id)
    work.mkdir(parents=True)
    write_job(work, THREE, [LAUGH, cut(6.1)])

    assert cli.main(["step", "enrich", str(job_id)]) == 0

    assert capsys.readouterr().out == f"{work / ENRICHED}\n"
    assert (work / ENRICHED).read_text(encoding="utf-8") == THREE_ENRICHED
