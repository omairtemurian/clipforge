"""Tests for the score step (SPEC 6.6): scored.json from candidates.json."""

import logging
from collections.abc import Sequence
from pathlib import Path

import pytest
from builders import event, source_meta
from clipforge import cli, process
from clipforge.config import Settings
from clipforge.models import (
    CandidateList,
    ClipCandidate,
    ContentGenre,
    ProcessingSettings,
    ScoredCandidate,
    ScoredList,
    Scores,
    SignalEvent,
    SignalList,
)
from clipforge.pipeline import score
from clipforge.pipeline.step import (
    CANDIDATES,
    META,
    SCORED,
    SIGNALS,
    STEP_NAMES,
    StepError,
    StepSettings,
    load_step,
    write_json,
)
from fakes import LLM_RESPONSE
from sqlalchemy import Engine

CFG = Settings(score_weights={"llm": 0.6, "laugh": 0.25, "energy": 0.15})
# llm_response.json: D 1.5-32.9 s, A 0.5-35.2, B 16.9-54.9, C 35.8-59.5 and
# E 0.5-16.3, with LLM averages D 64, A 82, B 73.5, C 68 and E 75.
D, A, B, C, E = CandidateList.model_validate_json(LLM_RESPONSE.read_bytes()).clips
# An energy peak over all of C and the last half of B.
PEAK = event("energy_peak", 35.8, 59.5)
# Two laughs a minute, so comedy for "auto"; the first follows D's and A's end.
LAUGHS = [event("laugh", 33.0, 34.0, 0.9), event("laugh", 5.0, 6.0, 0.5)]


def write_job(job_dir: Path, events: Sequence[SignalEvent]) -> None:
    """Write a job as curate leaves it for the 60 s fixture video: meta.json,
    signals.json with events and candidates.json with D, A, B, C and E."""
    write_json(job_dir / META, source_meta())
    write_json(job_dir / SIGNALS, SignalList(list(events)))
    write_json(job_dir / CANDIDATES, CandidateList(clips=[D, A, B, C, E]))


@pytest.fixture
def job(tmp_path: Path) -> Path:
    """A job directory as curate leaves it, with no signal events."""
    write_job(tmp_path, [])
    return tmp_path


def settings(
    progress: list[float] | None = None, cfg: Settings = CFG, **processing: object
) -> StepSettings:
    """StepSettings for score; progress, if given, collects reported progress."""
    return StepSettings(
        source="unused",
        processing=ProcessingSettings.model_validate(processing),
        cfg=cfg,
        on_progress=None if progress is None else progress.append,
    )


def written(job_dir: Path) -> list[ScoredCandidate]:
    """Return the clips of the job's scored.json."""
    return ScoredList.model_validate_json((job_dir / SCORED).read_bytes()).clips


def test_score_keeps_the_candidates_with_the_best_overall_scores(job: Path) -> None:
    write_job(job, [PEAK])
    progress: list[float] = []

    output = score.run(job, settings(progress, genre="podcast", num_clips=3))

    assert output == job / SCORED
    kept = written(job)
    assert [(c.title, c.scores.overall) for c in kept] == [
        (C.title, 74),
        (B.title, 69),
        (A.title, 66),
    ]
    assert kept[0].scores == Scores(
        overall=74, hook=70, flow=72, value=66, trend=64, laugh=0.0, energy=1.0
    )
    assert kept[1].scores.energy == 0.503
    assert [c.model_dump(exclude={"scores"}) for c in kept] == [
        C.model_dump(),
        B.model_dump(),
        A.model_dump(),
    ]
    assert progress == [1.0]


@pytest.mark.parametrize(
    ("genre", "ranking"),
    [
        ("auto", [(A, 71), (D, 61), (E, 45)]),
        ("comedy", [(A, 71), (D, 61), (E, 45)]),
        ("podcast", [(A, 66), (E, 60), (B, 59)]),
    ],
)
def test_laughs_after_the_end_lift_comedy_clips(
    job: Path, genre: str, ranking: list[tuple[ClipCandidate, int]]
) -> None:
    write_job(job, LAUGHS)

    score.run(job, settings(genre=genre, num_clips=3))

    kept = written(job)
    assert [(c.title, c.scores.overall) for c in kept] == [
        (c.title, overall) for c, overall in ranking
    ]
    assert kept[0].scores.laugh == 0.9


@pytest.mark.parametrize("genre", ["talk", "interview"])
def test_score_logs_the_weights_and_the_kept_clips(
    job: Path, genre: ContentGenre, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="clipforge.pipeline.score"):
        score.run(job, settings(genre=genre, num_clips=2))

    assert caplog.messages == [
        f"kept the best 2 of 5 candidates; {genre} weights: "
        "llm 0.80, laugh 0.00, energy 0.20",
        f"0.5-35.2s overall 66 (llm 0.83, laugh 0.00, energy 0.00): {A.title!r}",
        f"0.5-16.3s overall 60 (llm 0.76, laugh 0.00, energy 0.00): {E.title!r}",
    ]


def test_score_skips_a_job_with_scored_json_unless_forced(job: Path) -> None:
    write_json(job / SCORED, ScoredList(clips=[]))
    progress: list[float] = []

    score.run(job, settings(progress, genre="podcast", num_clips=1))
    assert written(job) == []

    score.run(job, settings(progress, genre="podcast", num_clips=1), force=True)
    assert [c.title for c in written(job)] == [A.title]
    assert progress == [1.0, 1.0]


def test_score_of_no_candidates_is_no_clips(job: Path) -> None:
    write_json(job / CANDIDATES, CandidateList(clips=[]))

    score.run(job, settings())

    assert written(job) == []


@pytest.mark.parametrize(
    ("missing", "step"),
    [(META, "ingest"), (SIGNALS, "signals"), (CANDIDATES, "curate")],
)
def test_score_needs_the_earlier_steps(job: Path, missing: str, step: str) -> None:
    write_json(job / SCORED, ScoredList(clips=[]))
    (job / missing).unlink()

    with pytest.raises(StepError, match=f"{missing} not found; run the {step} step"):
        score.run(job, settings(genre="podcast"), force=True)
    assert not (job / SCORED).exists()


def test_score_needs_weights_for_the_components_of_the_genre(job: Path) -> None:
    write_job(job, LAUGHS)
    # All three: pydantic-settings merges score_weights with config.yaml's.
    cfg = Settings(score_weights={"llm": 0.0, "laugh": 1.0, "energy": 0.0})

    with pytest.raises(StepError, match="no weight to llm, energy"):
        score.run(job, settings(cfg=cfg, genre="podcast"))
    assert not (job / SCORED).exists()

    score.run(job, settings(cfg=cfg, genre="comedy", num_clips=2))
    # Equal overall scores keep the order of candidates.json.
    assert [(c.title, c.scores.overall) for c in written(job)] == [
        (D.title, 89),
        (A.title, 89),
    ]


def test_score_is_the_step_after_curate() -> None:
    assert STEP_NAMES.index("score") == STEP_NAMES.index("curate") + 1
    assert load_step("score") is score.run


def test_step_command_runs_score_for_a_job(
    engine: Engine, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    job_id = process.create_job(engine, "video.mp4", ProcessingSettings(num_clips=2))
    work = data_dir / "work" / str(job_id)
    work.mkdir(parents=True)
    write_job(work, [PEAK])

    assert cli.main(["step", "score", str(job_id)]) == 0

    assert capsys.readouterr().out == f"{work / SCORED}\n"
    assert [c.title for c in written(work)] == [C.title, B.title]
