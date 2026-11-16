"""Tests for prompt to clip and keyword search (SPEC-v2 3.2).

Prompt to clip: the user's request goes into the curate system prompt, the
(fake) LLM's reply is checked against the ClipCandidate schema, and the
clips it keeps are snapped onto words. Keyword search: every place a term
is said in the fixture transcript is found without any LLM, and windows of
whole sentences are built around them.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from builders import source_meta
from clipforge.config import Settings
from clipforge.models import (
    CandidateList,
    ClipCandidate,
    ProcessingSettings,
    ScoredList,
    SignalList,
)
from clipforge.pipeline import curate, enrich, score, snap
from clipforge.pipeline.step import (
    CANDIDATES,
    META,
    SIGNALS,
    SNAPPED,
    TRANSCRIPT,
    StepSettings,
    write_json,
)
from fakes import FakeLLMClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REQUEST = "every time he talks about his gadgets"
CFG = Settings(clip_min_s=20, clip_max_s=75, max_clips_from_llm=30)


def step_settings(llm: FakeLLMClient | None, **processing: object) -> StepSettings:
    return StepSettings(
        source="unused",
        processing=ProcessingSettings.model_validate(processing),
        cfg=CFG,
        llm=llm,
    )


@pytest.fixture
def job(tmp_path: Path) -> Path:
    """A job directory as the steps up to enrich leave the fixture video."""
    write_json(tmp_path / META, source_meta())
    shutil.copy(FIXTURES / "transcript.json", tmp_path / TRANSCRIPT)
    write_json(tmp_path / SIGNALS, SignalList([]))
    enrich.run(tmp_path, step_settings(None), force=True)
    return tmp_path


def run_steps(job_dir: Path, settings: StepSettings) -> list[tuple[float, float]]:
    """Run curate, score and snap; return the (start, end) of snapped.json."""
    curate.run(job_dir, settings)
    score.run(job_dir, settings)
    snap.run(job_dir, settings)
    clips = ScoredList.model_validate_json((job_dir / SNAPPED).read_bytes()).clips
    return sorted((clip.start, clip.end) for clip in clips)


def candidates(job_dir: Path) -> list[ClipCandidate]:
    return CandidateList.model_validate_json((job_dir / CANDIDATES).read_bytes()).clips


def clip(start: float, end: float, **changes: Any) -> dict[str, Any]:
    """Return a reply clip from start to end seconds about the gadgets."""
    return {
        "start": start,
        "end": end,
        "title": "The fridge that judges you",
        "hook_text": "My fridge reports me",
        "description": "Smart gadgets have opinions.",
        "hashtags": ["comedy", "gadgets", "smarthome"],
        "emphasis_words": ["fridges"],
        "reason": "It is about his smart fridge and his car, as asked.",
        "hook": 80,
        "flow": 75,
        "value": 70,
        "trend": 65,
        **changes,
    }


def reply(*clips: dict[str, Any]) -> str:
    return json.dumps({"clips": list(clips)})


@pytest.fixture
def forbid_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(cfg: Settings) -> None:
        raise AssertionError("a keyword search must not create an LLM client")

    monkeypatch.setattr(curate, "create_client", forbidden)


def test_the_user_prompt_is_injected_into_the_curate_prompt(job: Path) -> None:
    llm = FakeLLMClient(reply())

    curate.run(job, step_settings(llm, genre="talk", keyword_prompt=f" {REQUEST}\n"))

    [(system, user)] = llm.calls
    assert f"The user is looking for: {REQUEST}\n" in system
    assert "Propose only moments that match this request" in system
    assert "says how it matches the request" in system
    assert "$" not in system.split("## Reply format")[0]
    assert "[00:16.9-00:19.7] S0: Then I bought one of those smart fridges." in user


def test_the_reply_is_validated_and_the_clips_are_snapped_to_words(
    job: Path,
) -> None:
    invalid = reply(clip(16.85, 41.2, hook=120, hashtags=["#gadgets"]))
    valid = reply(
        clip(16.85, 41.2),
        clip(36.0, 38.0, title="Too short for the auto range"),
    )
    llm = FakeLLMClient(invalid, valid)

    spans = run_steps(job, step_settings(llm, genre="talk", keyword_prompt=REQUEST))

    retry = llm.calls[1][1]
    assert "Your previous reply for this transcript was not valid" in retry
    assert "- clips.0.hook:" in retry and "- clips.0.hashtags.0:" in retry
    # 16.9 is when "Then" starts; "home." ends at 41.35 and the 0.3 s tail
    # stops before "Uh," starts at 42.1.
    assert spans == [(16.9, 41.65)]


def test_a_request_that_nothing_matches_gives_no_clips(job: Path) -> None:
    llm = FakeLLMClient(reply())
    assert run_steps(job, step_settings(llm, keyword_prompt="the moon landing")) == []


def test_a_keyword_search_finds_every_match_without_the_llm(
    job: Path, forbid_llm: None
) -> None:
    terms = ["body", "SMART  fridges", "night"]
    settings = step_settings(None, clipping="keyword_search", search_terms=terms)

    spans = run_steps(job, settings)

    # "body" (5.7 s, 9.6 s) and "smart fridges" (18.8 s) share the window of
    # the sentences 0-5; "night" (26.7 s, 28.0 s) opens one after it that
    # grows forward to 20 s. Snap adds each end's 0.3 s tail.
    assert spans == [(0.5, 22.75), (23.25, 51.85)]
    first, second = candidates(job)
    assert first.title == '"body" at 00:05.7'
    assert first.emphasis_words == ["body", "smart", "fridges"]
    assert first.hashtags == ["body", "smartfridges", "video", "clip", "shorts"]
    assert first.reason == (
        'Keyword search: "body", "SMART fridges" said at 00:05.7, 00:09.6, 00:18.8.'
    )
    assert first.description == "The teacher says, listen to your body."
    assert (first.hook, first.flow, first.value, first.trend) == (50, 50, 50, 50)
    assert second.title == '"night" at 00:26.7'


def test_a_keyword_search_is_deterministic(job: Path, forbid_llm: None) -> None:
    settings = step_settings(
        None, clipping="keyword_search", search_terms=["time"], length_presets=["lt30"]
    )
    curate.run(job, settings)
    first = (job / CANDIDATES).read_bytes()
    curate.run(job, settings, force=True)
    assert (job / CANDIDATES).read_bytes() == first
    # From the sentence of "time" (42.1 s) the shorter side is added each
    # step until the window is at least 20 s; the second "time" (56.2 s) is
    # then inside it.
    [found] = candidates(job)
    assert (found.start, found.end) == (35.8, 56.52)
    assert found.reason == 'Keyword search: "time" said at 00:45.5, 00:56.2.'


def test_a_keyword_search_keeps_to_the_timeframe(tmp_path: Path) -> None:
    write_json(tmp_path / META, source_meta(start=20, end=45, duration=60))
    shutil.copy(FIXTURES / "transcript.json", tmp_path / TRANSCRIPT)
    write_json(tmp_path / SIGNALS, SignalList([]))
    settings = step_settings(
        None, clipping="keyword_search", search_terms=["body", "night", "home"]
    )

    curate.run(tmp_path, settings)

    # "body" is said before the timeframe; the "night" window cannot reach
    # 20 s without the sentence of "home", which then joins it.
    [found] = candidates(tmp_path)
    assert (found.start, found.end) == (20.25, 41.35)
    assert found.emphasis_words == ["night", "home"]


def test_a_search_term_that_is_never_said_gives_no_clips(
    job: Path, forbid_llm: None
) -> None:
    settings = step_settings(None, clipping="keyword_search", search_terms=["moon"])
    assert run_steps(job, settings) == []
