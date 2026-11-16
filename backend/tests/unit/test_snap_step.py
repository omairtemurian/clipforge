"""Tests for the snap step (SPEC 6.7): snapped.json from scored.json."""

import logging
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest
from builders import FIXTURE_LAUGHS, source_meta
from clipforge import cli, process
from clipforge.models import (
    CandidateList,
    ClipCandidate,
    ProcessingSettings,
    ScoredCandidate,
    ScoredList,
    Scores,
    SignalEvent,
    SignalList,
    SourceMeta,
)
from clipforge.pipeline import snap
from clipforge.pipeline.step import (
    META,
    SCORED,
    SIGNALS,
    SNAPPED,
    STEP_NAMES,
    TRANSCRIPT,
    StepError,
    StepSettings,
    load_step,
    write_json,
)
from fakes import FIXTURES, LLM_RESPONSE
from sqlalchemy import Engine

# llm_response.json: A 0.5-35.2 s, B 16.9-54.9 and C 35.8-59.5, which score
# keeps for the fixture in this order.
_, A, B, C, _ = CandidateList.model_validate_json(LLM_RESPONSE.read_bytes()).clips


def scored(c: ClipCandidate, overall: int, **times: float) -> ScoredCandidate:
    """Return c, with its times replaced by times, as score keeps it with
    this overall score."""
    scores = Scores(
        overall=overall,
        hook=c.hook,
        flow=c.flow,
        value=c.value,
        trend=c.trend,
        laugh=0.5,
        energy=0.1,
    )
    return ScoredCandidate(**c.model_dump(), scores=scores).model_copy(update=times)


KEPT = [scored(A, 71), scored(B, 63), scored(C, 42)]
# A clip in the first laugh, between "floor?" and "Then".
NO_WORDS = scored(A, 30, start=13.6, end=16.5)


def write_job(
    job_dir: Path,
    clips: Sequence[ScoredCandidate] = KEPT,
    events: Sequence[SignalEvent] = FIXTURE_LAUGHS,
    meta: SourceMeta | None = None,
) -> None:
    """Write a job as score leaves it for the fixture video: meta.json, the
    fixture transcript, signals.json with events and scored.json with clips."""
    write_json(job_dir / META, source_meta() if meta is None else meta)
    shutil.copyfile(FIXTURES / "transcript.json", job_dir / TRANSCRIPT)
    write_json(job_dir / SIGNALS, SignalList(list(events)))
    write_json(job_dir / SCORED, ScoredList(clips=list(clips)))


@pytest.fixture
def job(tmp_path: Path) -> Path:
    """A job directory as score leaves it for the fixture video."""
    write_job(tmp_path)
    return tmp_path


def settings(progress: list[float] | None = None, **processing: object) -> StepSettings:
    """StepSettings for snap; progress, if given, collects reported progress."""
    return StepSettings(
        source="unused",
        processing=ProcessingSettings.model_validate(processing),
        on_progress=None if progress is None else progress.append,
    )


def written(job_dir: Path) -> list[ScoredCandidate]:
    """Return the clips of the job's snapped.json."""
    return ScoredList.model_validate_json((job_dir / SNAPPED).read_bytes()).clips


def test_without_clipping_the_timeframe_clip_is_kept_as_it_is(tmp_path: Path) -> None:
    whole = scored(A, 50, start=0.0, end=60.0)
    write_job(tmp_path, clips=[whole, NO_WORDS])
    progress: list[float] = []

    snap.run(tmp_path, settings(progress, clipping="captions_only"))

    assert written(tmp_path) == [whole, NO_WORDS]
    assert progress == [1.0]


@pytest.mark.parametrize(
    ("genre", "ends"),
    [
        # Three laughs a minute: comedy. A and B end in the laugh after
        # their last word, 1.5 s after it.
        ("auto", [34.35, 53.05, 59.8]),
        ("comedy", [34.35, 53.05, 59.8]),
        ("podcast", [33.15, 51.85, 59.8]),
    ],
)
def test_snap_cuts_the_clips_that_score_kept_between_words(
    job: Path, genre: str, ends: list[float]
) -> None:
    progress: list[float] = []

    output = snap.run(job, settings(progress, genre=genre))

    assert output == job / SNAPPED
    clips = written(job)
    assert [(c.start, c.end) for c in clips] == list(
        zip([0.5, 16.9, 35.8], ends, strict=True)
    )
    assert [c.model_dump(exclude={"start", "end"}) for c in clips] == [
        c.model_dump(exclude={"start", "end"}) for c in KEPT
    ]
    assert progress == [1.0]


def test_snap_logs_each_clip_and_drops_a_clip_without_words(
    job: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_job(job, [KEPT[0], NO_WORDS])

    with caplog.at_level(logging.INFO, logger="clipforge.pipeline.snap"):
        snap.run(job, settings(genre="comedy"))

    assert [c.title for c in written(job)] == [A.title]
    assert [(r.levelname, r.message) for r in caplog.records] == [
        ("INFO", f"snapped 0.5-35.2s to 0.5-34.35s: {A.title!r}"),
        ("WARNING", f"dropped 13.6-16.5s: no word starts in it: {A.title!r}"),
    ]


def test_snap_uses_the_words_and_the_end_of_the_timeframe(job: Path) -> None:
    # "Hi" (0.5 s) begins a segment that starts before the timeframe.
    clips = [scored(A, 71, start=0.6, end=35.2), KEPT[2]]
    write_job(job, clips, meta=source_meta(0.6, 59.6, duration=60.0))

    snap.run(job, settings(genre="podcast"))

    assert [(c.start, c.end) for c in written(job)] == [(1.53, 33.15), (35.8, 59.6)]


def test_snap_skips_a_job_with_snapped_json_unless_forced(job: Path) -> None:
    write_json(job / SNAPPED, ScoredList(clips=[]))
    progress: list[float] = []

    snap.run(job, settings(progress, genre="podcast"))
    assert written(job) == []

    snap.run(job, settings(progress, genre="podcast"), force=True)
    assert [c.title for c in written(job)] == [A.title, B.title, C.title]
    assert progress == [1.0, 1.0]


def test_snap_of_no_clips_is_no_clips(job: Path) -> None:
    write_job(job, [])

    snap.run(job, settings())

    assert written(job) == []


@pytest.mark.parametrize(
    ("missing", "step"),
    [
        (META, "ingest"),
        (TRANSCRIPT, "transcribe"),
        (SIGNALS, "signals"),
        (SCORED, "score"),
    ],
)
def test_snap_needs_the_earlier_steps(job: Path, missing: str, step: str) -> None:
    write_json(job / SNAPPED, ScoredList(clips=[]))
    (job / missing).unlink()

    with pytest.raises(StepError, match=f"{missing} not found; run the {step} step"):
        snap.run(job, settings(genre="podcast"), force=True)
    assert not (job / SNAPPED).exists()


def test_snap_is_the_step_after_score() -> None:
    assert STEP_NAMES.index("snap") == STEP_NAMES.index("score") + 1
    assert load_step("snap") is snap.run


def test_step_command_runs_snap_for_a_job(
    engine: Engine, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    job_id = process.create_job(engine, "video.mp4", ProcessingSettings())
    work = data_dir / "work" / str(job_id)
    work.mkdir(parents=True)
    write_job(work)

    assert cli.main(["step", "snap", str(job_id)]) == 0

    assert capsys.readouterr().out == f"{work / SNAPPED}\n"
    assert [(c.start, c.end) for c in written(work)] == [
        (0.5, 34.35),
        (16.9, 53.05),
        (35.8, 59.8),
    ]
