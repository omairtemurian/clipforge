"""Tests for the clip length presets, custom range, timeframe and clip count
(SPEC-v2 3.2), run on the fixture transcript and recorded LLM reply."""

import shutil
from pathlib import Path

import pytest
from builders import source_meta
from clipforge.candidate_rules import length_range, validate_candidate
from clipforge.config import Settings
from clipforge.models import (
    CandidateList,
    ClipCandidate,
    ProcessingSettings,
    ScoredList,
    SignalList,
    SourceMeta,
)
from clipforge.pipeline import curate, enrich, score
from clipforge.pipeline.curate_prompt import length_rule
from clipforge.pipeline.step import (
    CANDIDATES,
    META,
    SCORED,
    SIGNALS,
    TRANSCRIPT,
    StepSettings,
    write_json,
)
from fakes import LLM_RESPONSE, FakeLLMClient
from pydantic import ValidationError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CFG = Settings(clip_min_s=20, clip_max_s=75, chunk_minutes=10, chunk_overlap_s=60)
# llm_response.json: D 1.5-32.9 s, A 0.5-35.2, B 16.9-54.9, C 35.8-59.5 and
# E 0.5-16.3 (lengths 31.4, 34.7, 38.0, 23.7 and 15.8 s). Curate drops D as a
# duplicate of the better A.
D, A, B, C, E = CandidateList.model_validate_json(LLM_RESPONSE.read_bytes()).clips


def step_settings(llm: FakeLLMClient | None, **processing: object) -> StepSettings:
    return StepSettings(
        source="unused",
        processing=ProcessingSettings.model_validate(processing),
        cfg=CFG,
        llm=llm,
    )


def make_job(job_dir: Path, meta: SourceMeta) -> None:
    """Write the job as the steps up to enrich leave it for the fixture video."""
    write_json(job_dir / META, meta)
    shutil.copy(FIXTURES / "transcript.json", job_dir / TRANSCRIPT)
    write_json(job_dir / SIGNALS, SignalList([]))
    enrich.run(job_dir, step_settings(None), force=True)


def curated(job_dir: Path, **processing: object) -> list[ClipCandidate]:
    """Run curate on the recorded reply and return the candidates it keeps."""
    curate.run(job_dir, step_settings(FakeLLMClient(), **processing))
    return CandidateList.model_validate_json((job_dir / CANDIDATES).read_bytes()).clips


def titles(clips: list[ClipCandidate]) -> set[str]:
    return {c.title for c in clips}


@pytest.fixture
def job(tmp_path: Path) -> Path:
    make_job(tmp_path, source_meta())
    return tmp_path


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("0_60", (0.0, 60.0)),
        ("60_180", (60.0, 180.0)),
        ("180_300", (180.0, 300.0)),
        ("300_600", (300.0, 600.0)),
        ("600_900", (600.0, 900.0)),
    ],
)
def test_the_v2_presets_cover_zero_to_fifteen_minutes(
    preset: str, expected: tuple[float, float]
) -> None:
    assert length_range(preset, CFG) == expected  # type: ignore[arg-type]


def test_the_v1_presets_are_still_known() -> None:
    for preset in ("lt30", "30_60", "60_90", "90_180"):
        assert length_range(preset, CFG)[0] < length_range(preset, CFG)[1]  # type: ignore[arg-type]


def test_a_custom_range_is_inclusive_and_checked_like_a_preset() -> None:
    candidate = ClipCandidate.model_validate(
        {**A.model_dump(), "start": 0.0, "end": 45.0}
    )
    assert validate_candidate(candidate, 60.0, ["custom"], CFG, (45.0, 50.0))[0]
    ok, reason = validate_candidate(candidate, 60.0, ["custom"], CFG, (46.0, 50.0))
    assert not ok
    assert "custom (46-50s)" in reason


def test_a_custom_preset_without_a_range_is_an_error() -> None:
    with pytest.raises(ValueError, match="needs a custom range"):
        length_range("custom", CFG)


@pytest.mark.parametrize(
    "bad",
    [
        {"custom_length_min_s": 60, "custom_length_max_s": 60},
        {"custom_length_min_s": 90, "custom_length_max_s": 30},
        {"custom_length_min_s": 10, "custom_length_max_s": 901},
        {"custom_length_min_s": -1, "custom_length_max_s": 30},
    ],
)
def test_a_custom_range_needs_min_below_max_and_max_at_most_900(
    bad: dict[str, float],
) -> None:
    with pytest.raises(ValidationError):
        ProcessingSettings.model_validate({"length_presets": ["custom"], **bad})


def test_the_custom_preset_needs_both_bounds() -> None:
    with pytest.raises(ValidationError, match="custom_length_min_s"):
        ProcessingSettings.model_validate({"length_presets": ["custom"]})
    with pytest.raises(ValidationError, match="custom_length_min_s"):
        ProcessingSettings.model_validate(
            {"length_presets": ["custom"], "custom_length_min_s": 5}
        )


def test_a_valid_custom_range_is_kept_and_reaches_the_prompt() -> None:
    settings = ProcessingSettings.model_validate(
        {
            "length_presets": ["custom", "0_60"],
            "custom_length_min_s": 20,
            "custom_length_max_s": 900,
        }
    )
    assert settings.length_presets == ["0_60", "custom"]
    assert settings.custom_length == (20.0, 900.0)
    rule = length_rule(settings.length_presets, CFG, settings.custom_length)
    assert rule == "0 to 60 seconds or 20 to 900 seconds"


def test_the_one_minute_preset_keeps_the_short_clip_that_auto_drops(job: Path) -> None:
    assert titles(curated(job, length_presets=["0_60"])) == titles([A, B, C, E])


def test_a_custom_range_selects_only_the_clips_inside_it(job: Path) -> None:
    kept = curated(
        job,
        length_presets=["custom"],
        custom_length_min_s=30,
        custom_length_max_s=35,
    )
    assert titles(kept) == titles([A])


def test_a_custom_range_can_be_combined_with_a_preset(job: Path) -> None:
    kept = curated(
        job,
        length_presets=["lt30", "custom"],
        custom_length_min_s=37,
        custom_length_max_s=40,
    )
    assert titles(kept) == titles([E, C, B])


def test_a_range_no_clip_fits_keeps_nothing(job: Path) -> None:
    assert curated(job, length_presets=["60_180"]) == []


def test_the_timeframe_limits_the_clips(tmp_path: Path) -> None:
    make_job(tmp_path, source_meta(start=30))

    kept = curated(tmp_path, length_presets=["0_60"], timeframe_start=30)

    assert titles(kept) == titles([C])
    assert all(c.start >= 30 for c in kept)


def test_the_timeframe_end_limits_the_clips(tmp_path: Path) -> None:
    make_job(tmp_path, source_meta(end=36, duration=60))

    kept = curated(tmp_path, length_presets=["0_60"], timeframe_end=36)

    assert titles(kept) == titles([A, E])
    assert all(c.end <= 36 for c in kept)


@pytest.mark.parametrize("count", [1, 2, 4])
def test_the_clip_count_limits_the_scored_clips(job: Path, count: int) -> None:
    chosen = step_settings(FakeLLMClient(), length_presets=["0_60"], num_clips=count)
    curate.run(job, chosen)
    score.run(job, chosen)

    scored = ScoredList.model_validate_json((job / SCORED).read_bytes()).clips

    assert len(scored) == count
    best_first = [c.scores.overall for c in scored]
    assert best_first == sorted(best_first, reverse=True)


def test_asking_for_more_clips_than_exist_keeps_all(job: Path) -> None:
    chosen = step_settings(FakeLLMClient(), length_presets=["0_60"], num_clips=30)
    curate.run(job, chosen)
    score.run(job, chosen)

    assert len(ScoredList.model_validate_json((job / SCORED).read_bytes()).clips) == 4
