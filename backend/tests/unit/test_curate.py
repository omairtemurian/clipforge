"""Tests for the curate step (SPEC 6.5): windows, retries and candidates.json.

The LLM is FakeLLMClient (canned replies) or a real client on FakeLLMServer.
"""

import json
import logging
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest
from builders import cut, event, source_meta
from clipforge.config import Settings
from clipforge.llm import LLMClient, OpenAICompatClient
from clipforge.models import (
    CandidateList,
    ClipCandidate,
    ProcessingSettings,
    SignalEvent,
    SignalList,
    SourceMeta,
    Transcript,
)
from clipforge.pipeline import enrich
from clipforge.pipeline.curate import (
    Window,
    ask_window,
    parse_reply,
    plan_windows,
    run,
)
from clipforge.pipeline.enrich import PromptLine
from clipforge.pipeline.step import (
    CANDIDATES,
    ENRICHED,
    META,
    SIGNALS,
    TRANSCRIPT,
    StepError,
    StepSettings,
    write_json,
)
from fakes import LLM_RESPONSE, FakeLLMClient, FakeLLMServer

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CFG = Settings(
    clip_min_s=20,
    clip_max_s=75,
    chunk_minutes=10,
    chunk_overlap_s=60,
    max_clips_from_llm=30,
)
REPLY = LLM_RESPONSE.read_text(encoding="utf-8")
CLIPS = CandidateList.model_validate_json(REPLY).clips
# What curate keeps of llm_response.json (see test_curate_select).
KEPT = [CLIPS[1], CLIPS[2], CLIPS[3]]
WINDOW = Window(0, 600, [PromptLine(0.5, "[00:00.5-00:01.4] S0: Hi everyone.")])
NOT_JSON = "Sure! Here are the clips."


def lines_every_10s(count: int) -> list[PromptLine]:
    return [PromptLine(10.0 * k, f"line {k}") for k in range(count)]


def enrich_job(
    job_dir: Path, meta: SourceMeta, events: Sequence[SignalEvent] = ()
) -> None:
    """Write meta.json and signals.json, and enriched.txt for them (enrich)."""
    write_json(job_dir / META, meta)
    write_json(job_dir / SIGNALS, SignalList(list(events)))
    enrich.run(job_dir, settings(None), force=True)


@pytest.fixture
def job(tmp_path: Path) -> Path:
    """A job directory as the steps up to enrich leave it for the fixture
    video, with no signal events."""
    shutil.copy(FIXTURES / "transcript.json", tmp_path / TRANSCRIPT)
    enrich_job(tmp_path, source_meta())
    return tmp_path


def settings(
    llm: LLMClient | None,
    cfg: Settings = CFG,
    progress: list[float] | None = None,
    **processing: object,
) -> StepSettings:
    """StepSettings for curate; progress, if given, collects reported progress."""
    return StepSettings(
        source="unused",
        processing=ProcessingSettings.model_validate(processing),
        cfg=cfg,
        on_progress=None if progress is None else progress.append,
        llm=llm,
    )


def written(job_dir: Path) -> list[ClipCandidate]:
    return CandidateList.model_validate_json((job_dir / CANDIDATES).read_bytes()).clips


def test_a_25_minute_transcript_gives_three_overlapping_windows() -> None:
    windows = plan_windows(lines_every_10s(150), 0, 1500, CFG)
    assert [(w.start, w.end) for w in windows] == [(0, 600), (540, 1140), (1080, 1500)]
    first_last = [(w.lines[0].start, w.lines[-1].start) for w in windows]
    assert first_last == [(0, 590), (540, 1130), (1080, 1490)]


def test_windows_grow_to_hold_the_longest_chosen_clip() -> None:
    windows = plan_windows(lines_every_10s(300), 0, 3000, CFG, longest=900)
    assert [(w.start, w.end) for w in windows] == [(0, 1800), (900, 2700), (1800, 3000)]


def test_the_outer_windows_take_lines_rounded_out_of_the_timeframe() -> None:
    # enriched.txt shows a line that starts at 30.04 s as 00:30.0.
    lines = [PromptLine(30, "first"), PromptLine(600, "both"), PromptLine(1200, "last")]
    windows = plan_windows(lines, 30.04, 1199.96, CFG)
    texts = [[line.text for line in window.lines] for window in windows]
    assert texts == [["first", "both"], ["both"], ["last"]]


def test_bad_chunk_settings_raise_step_error() -> None:
    cfg = Settings(chunk_minutes=1, chunk_overlap_s=60)
    with pytest.raises(StepError, match="cannot cut the transcript into windows"):
        plan_windows([], 0, 100, cfg)


@pytest.mark.parametrize(
    "reply", [REPLY, f"```json\n{REPLY}```", f"\n```\n{REPLY}\n```\n"]
)
def test_parse_reply_reads_plain_and_code_block_json(reply: str) -> None:
    assert parse_reply(reply) == CLIPS


def test_an_invalid_reply_is_retried_with_its_validation_error() -> None:
    fake = FakeLLMClient(NOT_JSON, REPLY)
    assert ask_window(fake, "system", WINDOW) == CLIPS
    (system1, user1), (system2, user2) = fake.calls
    assert system1 == system2 == "system"
    assert user2.startswith(f"{user1}\n\n")
    assert "- reply: Invalid JSON: expected value at line 1 column 1" in user2


def test_a_schema_error_is_sent_back_with_the_path_of_the_bad_value() -> None:
    reply = json.loads(REPLY)
    reply["clips"][0]["title"] = "x" * 71
    fake = FakeLLMClient(json.dumps(reply), REPLY)
    assert ask_window(fake, "system", WINDOW) == CLIPS
    retry = fake.calls[1][1]
    assert "- clips.0.title: String should have at most 70 characters" in retry


def test_a_window_is_skipped_after_three_invalid_replies(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeLLMClient(NOT_JSON, "[]", '{"clips": "none"}')
    with caplog.at_level(logging.WARNING, logger="clipforge.pipeline.curate"):
        assert ask_window(fake, "system", WINDOW) is None
    assert len(fake.calls) == 3
    assert "reply 3 of 3 is not valid" in caplog.text
    assert "skipped window 00:00.0-10:00.0" in caplog.text


def test_a_window_without_lines_is_not_sent() -> None:
    fake = FakeLLMClient(REPLY)
    assert ask_window(fake, "system", Window(0, 600, [])) == []
    assert fake.calls == []


def test_run_writes_the_kept_candidates_best_first(job: Path) -> None:
    fake = FakeLLMClient()
    progress: list[float] = []
    assert run(job, settings(fake, progress=progress)) == job / CANDIDATES
    assert written(job) == KEPT
    assert progress == [1.0]
    [(system, user)] = fake.calls
    assert "end minus start must be 20 to 180 seconds (most often 20 to 75" in system
    lines = user.splitlines()
    assert len(lines) == 14
    assert lines[0] == "[00:00.5-00:01.4] S0: Hi everyone."


def test_run_without_clipping_makes_the_timeframe_one_clip(tmp_path: Path) -> None:
    write_json(tmp_path / META, source_meta(start=5, end=50, duration=60))
    fake = FakeLLMClient(NOT_JSON)
    run(tmp_path, settings(fake, clipping="captions_only"))
    [clip] = written(tmp_path)
    assert (clip.start, clip.end, clip.title, clip.hook_text) == (5, 50, "sample", "")
    assert fake.calls == []


def test_run_follows_the_length_preset_and_keyword_prompt(job: Path) -> None:
    fake = FakeLLMClient()
    run(job, settings(fake, length_presets=["lt30"], keyword_prompt="smart homes"))
    assert written(job) == [CLIPS[4], CLIPS[3]]
    system = fake.calls[0][0]
    assert "under 30 seconds" in system
    assert "The user is looking for: smart homes" in system


def test_run_sends_the_lines_of_enriched_txt_with_their_markers(job: Path) -> None:
    enrich_job(job, source_meta(), [event("laugh", 13.8, 16.3, 0.9), cut(36)])
    fake = FakeLLMClient()
    run(job, settings(fake, genre="podcast"))
    user = fake.calls[0][1]
    assert user == (job / ENRICHED).read_text(encoding="utf-8").rstrip("\n")
    assert user.count("[LAUGH 2.5s 0.90]") == user.count("[SCENE CUT]") == 1


@pytest.mark.parametrize(
    ("extra", "error"),
    [
        (b"\nHi everyone.\n", "line 16 is not valid: 'Hi everyone.' does not start"),
        (b"[00:59.0-00:59.5] S0: \xff\n", "enriched.txt is not UTF-8 text"),
    ],
)
def test_run_rejects_an_enriched_txt_that_enrich_did_not_write(
    job: Path, extra: bytes, error: str
) -> None:
    with (job / ENRICHED).open("ab") as enriched:
        enriched.write(extra)
    with pytest.raises(StepError, match=error):
        run(job, settings(FakeLLMClient()))


def test_run_sends_only_the_timeframe(job: Path) -> None:
    enrich_job(job, source_meta(start=30))
    fake = FakeLLMClient()
    run(job, settings(fake))
    assert written(job) == [CLIPS[3]]
    lines = fake.calls[0][1].splitlines()
    assert len(lines) == 6
    assert lines[0] == "[00:35.8-00:38.4] S0: My car has a voice assistant now."


def test_run_caps_the_candidates(job: Path) -> None:
    cfg = CFG.model_copy(update={"max_clips_from_llm": 2})
    run(job, settings(FakeLLMClient(), cfg))
    assert written(job) == KEPT[:2]


def test_run_survives_a_skipped_window(
    job: Path, caplog: pytest.LogCaptureFixture
) -> None:
    transcript = Transcript.model_validate_json((job / TRANSCRIPT).read_bytes())
    later = [
        s.model_copy(update={"start": s.start + 360, "end": s.end + 360})
        for s in transcript.segments
    ]
    transcript.segments += later
    write_json(job / TRANSCRIPT, transcript)
    enrich_job(job, source_meta(end=420))
    # Clips of up to 180 s ("auto") make the windows 360 s long.
    cfg = CFG.model_copy(update={"chunk_minutes": 1, "chunk_overlap_s": 0})
    fake = FakeLLMClient(NOT_JSON, NOT_JSON, NOT_JSON, REPLY)
    with caplog.at_level(logging.INFO, logger="clipforge.pipeline.curate"):
        run(job, settings(fake, cfg))
    assert written(job) == KEPT
    assert fake.calls[3][1].startswith("[06:00.5-06:01.4] S0: Hi everyone.")
    assert "skipped window 00:00.0-06:00.0" in caplog.text
    assert "kept 3 of 5 clip candidates; 1 of 2 windows skipped" in caplog.text


def test_run_writes_no_candidates_when_every_window_fails(job: Path) -> None:
    run(job, settings(FakeLLMClient(NOT_JSON, repeat_last=True)))
    assert written(job) == []


def test_run_skips_when_candidates_exist_unless_forced(job: Path) -> None:
    (job / CANDIDATES).write_text('{"clips": []}', encoding="utf-8")
    fake = FakeLLMClient()
    progress: list[float] = []
    step = settings(fake, progress=progress)
    run(job, step)
    assert (fake.calls, progress, written(job)) == ([], [1.0], [])
    run(job, step, force=True)
    assert written(job) == KEPT


def test_run_turns_an_llm_failure_into_step_error(job: Path) -> None:
    server = FakeLLMServer(500, text="boom")
    llm = OpenAICompatClient("http://llm.test/v1", "", "m", transport=server.transport)
    with pytest.raises(StepError, match="the LLM request failed: .*500"):
        run(job, settings(llm))
    assert not (job / CANDIDATES).exists()


def test_run_uses_the_configured_llm_by_default(job: Path) -> None:
    cfg = CFG.model_copy(
        update={"llm_provider": "ollama", "ollama_host": "http://127.0.0.1:9"}
    )
    with pytest.raises(StepError, match="the LLM request failed"):
        run(job, settings(None, cfg))


@pytest.mark.parametrize(
    ("missing", "step"), [(META, "ingest"), (ENRICHED, "enrich"), (SIGNALS, "signals")]
)
def test_run_needs_the_earlier_steps(job: Path, missing: str, step: str) -> None:
    (job / missing).unlink()
    with pytest.raises(StepError, match=f"not found; run the {step} step first"):
        run(job, settings(FakeLLMClient()))
