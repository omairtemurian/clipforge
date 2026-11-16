"""Tests for the captions_only clipping mode (SPEC-v2 3.1): the whole video
or timeframe is one clip, and no LLM is asked."""

import shutil
from pathlib import Path

import pytest
from builders import source_meta
from clipforge.config import Settings
from clipforge.models import (
    CandidateList,
    ProcessingSettings,
    ScoredList,
    SignalList,
    SourceMeta,
)
from clipforge.pipeline import curate, enrich, score, snap
from clipforge.pipeline.step import (
    CANDIDATES,
    META,
    SCORED,
    SIGNALS,
    SNAPPED,
    TRANSCRIPT,
    StepSettings,
    write_json,
)
from fakes import FakeLLMClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def step_settings(llm: FakeLLMClient | None, **processing: object) -> StepSettings:
    return StepSettings(
        source="unused",
        processing=ProcessingSettings.model_validate(processing),
        cfg=Settings(),
        llm=llm,
    )


def make_job(job_dir: Path, meta: SourceMeta) -> None:
    """Write the job as the steps up to enrich leave it for the fixture video."""
    write_json(job_dir / META, meta)
    shutil.copy(FIXTURES / "transcript.json", job_dir / TRANSCRIPT)
    write_json(job_dir / SIGNALS, SignalList([]))
    enrich.run(job_dir, step_settings(None), force=True)


def run_steps(job_dir: Path, llm: FakeLLMClient, **processing: object) -> ScoredList:
    """Run curate, score and snap in captions_only mode and return snapped.json."""
    chosen = step_settings(llm, clipping="captions_only", **processing)
    curate.run(job_dir, chosen)
    score.run(job_dir, chosen)
    snap.run(job_dir, chosen)
    return ScoredList.model_validate_json((job_dir / SNAPPED).read_bytes())


def test_the_whole_video_is_one_clip_and_the_llm_is_not_asked(tmp_path: Path) -> None:
    make_job(tmp_path, source_meta())
    llm = FakeLLMClient()

    [clip] = run_steps(tmp_path, llm).clips

    assert (clip.start, clip.end, clip.title) == (0.0, 60.0, "sample")
    assert llm.calls == []


def test_the_chosen_timeframe_is_the_one_clip(tmp_path: Path) -> None:
    make_job(tmp_path, source_meta(start=10, end=45, duration=60))
    llm = FakeLLMClient()

    [clip] = run_steps(tmp_path, llm, num_clips=5).clips

    assert (clip.start, clip.end) == (10.0, 45.0)
    assert llm.calls == []


def test_no_client_is_made_without_one_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(cfg: Settings) -> None:
        raise AssertionError("captions_only must not create an LLM client")

    monkeypatch.setattr(curate, "create_client", forbidden)
    make_job(tmp_path, source_meta())

    curate.run(tmp_path, step_settings(None, clipping="captions_only"))

    clips = CandidateList.model_validate_json((tmp_path / CANDIDATES).read_bytes())
    assert len(clips.clips) == 1
    assert (tmp_path / SCORED).exists() is False


def test_the_clipping_none_of_saved_settings_reads_as_captions_only() -> None:
    saved = ProcessingSettings.model_validate({"clipping": "none"})
    assert saved.clipping == "captions_only"
    assert ProcessingSettings().clipping == "ai"
