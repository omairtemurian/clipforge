"""Tests of topic chapters (SPEC-v2 3.2): the (fake) LLM's chapters are
validated, snapped to the sentences of the fixture transcript and made
contiguous, and curate can be restricted to the ranges of chosen chapters.

The fixture transcript has three topics: yoga (0.5-13.5 s), the fridge
(16.9-32.85 s) and the car and the goodbye (35.8-59.5 s).
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from builders import source_meta
from clipforge.config import Settings
from clipforge.llm_http import LLMError
from clipforge.models import (
    CandidateList,
    Chapter,
    ChapterDraft,
    ProcessingSettings,
    Segment,
    SignalList,
    Transcript,
)
from clipforge.pipeline import chapters as chapters_module
from clipforge.pipeline import curate, enrich
from clipforge.pipeline.chapters import (
    ChapterLLMError,
    chapter_ranges,
    check_reply,
    make_chapters,
    read_chapters,
    sentences,
)
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.step import (
    CANDIDATES,
    CHAPTERS,
    META,
    SIGNALS,
    TRANSCRIPT,
    StepError,
    StepSettings,
    write_json,
)
from fakes import FakeLLMClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CFG = Settings(clip_min_s=10, clip_max_s=75, max_clips_from_llm=30)


def draft(start: float, end: float, title: str, summary: str = "") -> dict[str, Any]:
    return {"start": start, "end": end, "title": title, "summary": summary}


def reply(*chapters: dict[str, Any]) -> str:
    return json.dumps({"chapters": list(chapters)})


YOGA = draft(0.5, 16.9, "Yoga", "He tries yoga.")
FRIDGE = draft(16.9, 35.8, "The smart fridge", "His fridge reports on him.")
CAR = draft(35.8, 59.5, "The car", "The voice assistant and the goodbye.")
THREE = reply(YOGA, FRIDGE, CAR)


@pytest.fixture
def job(tmp_path: Path) -> Path:
    """A job directory as the steps up to enrich leave the fixture video."""
    write_json(tmp_path / META, source_meta())
    shutil.copy(FIXTURES / TRANSCRIPT, tmp_path / TRANSCRIPT)
    write_json(tmp_path / SIGNALS, SignalList([]))
    enrich.run(tmp_path, StepSettings(source="unused", cfg=CFG), force=True)
    return tmp_path


def spans(found: list[Chapter]) -> list[tuple[int, float, float]]:
    return [(c.id, c.start, c.end) for c in found]


def test_chapters_are_contiguous_and_start_at_sentences(job: Path) -> None:
    llm = FakeLLMClient(THREE)

    found = make_chapters(job, CFG, llm)

    assert spans(found) == [(1, 0.5, 16.9), (2, 16.9, 35.8), (3, 35.8, 59.5)]
    assert [c.title for c in found] == ["Yoga", "The smart fridge", "The car"]
    assert found[1].summary == "His fridge reports on him."
    assert read_chapters(job) == found
    assert (job / CHAPTERS).is_file()
    [(system, user)] = llm.calls
    assert '{"chapters": [...]}' in system and "$" not in system
    assert "[00:16.9-00:19.7] S0: Then I bought one of those smart fridges." in user


def test_chapter_times_snap_to_the_nearest_sentence_start(job: Path) -> None:
    rough = reply(
        draft(0.0, 15.0, "Yoga"),
        draft(17.0, 35.0, "The smart fridge"),
        draft(35.6, 60.0, "The car"),
    )

    found = make_chapters(job, CFG, FakeLLMClient(rough))

    # The first chapter takes the first sentence (0.5); 17.0 is nearest to the
    # sentence at 16.9 and 35.6 to the one at 35.8.
    assert spans(found) == [(1, 0.5, 16.9), (2, 16.9, 35.8), (3, 35.8, 59.5)]


def test_chapters_that_snap_to_one_sentence_become_one(job: Path) -> None:
    close = reply(
        draft(0.5, 17.0, "Yoga"),
        draft(17.0, 17.05, "A wobble"),
        draft(17.05, 59.5, "Also the fridge"),
    )

    found = make_chapters(job, CFG, FakeLLMClient(close))

    assert [(c.title, c.start) for c in found] == [("Yoga", 0.5), ("A wobble", 16.9)]


def test_a_reply_with_overlap_or_a_gap_is_sent_back(job: Path) -> None:
    overlapping = reply(draft(0.5, 20.0, "Yoga"), draft(16.9, 59.5, "The rest"))
    gap = reply(draft(0.5, 13.5, "Yoga"), draft(35.8, 59.5, "The car"))
    llm = FakeLLMClient(overlapping, gap, THREE)

    found = make_chapters(job, CFG, llm)

    assert len(found) == 3
    assert len(llm.calls) == 3
    first_retry, second_retry = llm.calls[1][1], llm.calls[2][1]
    assert "Your previous reply for this transcript was not valid" in first_retry
    assert "- chapter 2 starts at 16.9s, before chapter 1 ends at 20s" in first_retry
    assert "- the sentence at 16.9s is in no chapter" in second_retry
    assert "- the sentence at 27.65s is in no chapter" in second_retry


def test_an_unparsable_reply_is_sent_back_with_its_errors(job: Path) -> None:
    broken = reply(draft(0.5, 59.5, ""))
    llm = FakeLLMClient("not json", broken, THREE)

    assert len(make_chapters(job, CFG, llm)) == 3

    assert "- chapters.0.title:" in llm.calls[2][1]


def test_a_part_without_a_valid_reply_fails(job: Path) -> None:
    llm = FakeLLMClient(reply(), repeat_last=True)

    with pytest.raises(ChapterLLMError, match="no valid chapters"):
        make_chapters(job, CFG, llm)

    assert len(llm.calls) == MAX_RETRIES + 1
    assert not (job / CHAPTERS).exists()


def test_an_llm_that_cannot_be_reached_fails(job: Path) -> None:
    class Down:
        def complete_json(self, system: str, user: str) -> str:
            raise LLMError("the LLM is down")

    with pytest.raises(ChapterLLMError, match="the LLM is down"):
        make_chapters(job, CFG, Down())


def test_a_long_video_is_asked_part_by_part_and_the_parts_join(
    job: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chapters_module, "CHAPTER_WINDOW_S", 30.0)
    llm = FakeLLMClient(
        reply(draft(0.5, 16.9, "Yoga"), draft(16.9, 32.9, "The fridge")),
        reply(draft(35.8, 59.5, "The car")),
    )

    found = make_chapters(job, CFG, llm)

    assert spans(found) == [(1, 0.5, 16.9), (2, 16.9, 35.8), (3, 35.8, 59.5)]
    first, second = (user for _, user in llm.calls)
    assert "00:35.8" not in first and "00:00.5" not in second
    assert "My car has a voice assistant now." in second


def test_a_transcript_without_speech_has_no_chapters(job: Path) -> None:
    write_json(job / META, source_meta(start=59.9, end=60.0))

    with pytest.raises(StepError, match="no speech"):
        make_chapters(job, CFG, FakeLLMClient(THREE))


def test_check_reply_accepts_a_rounded_overlap_and_lists_problems(job: Path) -> None:
    transcript = Transcript.model_validate_json((job / TRANSCRIPT).read_bytes())
    part = sentences(transcript.segments)
    rounded = [
        ChapterDraft(start=0.5, end=16.95, title="a"),
        ChapterDraft(start=16.9, end=59.6, title="b"),
    ]
    assert check_reply(rounded, part) == []

    backwards = [ChapterDraft(start=5, end=3, title="a")]
    problems = check_reply(backwards, part)
    assert problems[0] == "- chapter 1 ends before it starts"
    assert len(problems) == 1 + len(part)
    many = [
        Segment(id=i, start=i, end=i + 0.5, text="Hi", words=[], speaker="S0")
        for i in range(30)
    ]
    capped = check_reply([ChapterDraft(start=100, end=101, title="a")], many)
    assert len(capped) == 21 and capped[-1] == "- ... and 10 more"
    assert check_reply([], part) == ["- chapters: the reply has no chapters"]


def chapter(number: int, start: float, end: float) -> Chapter:
    return Chapter(id=number, start=start, end=end, title=f"c{number}", summary="")


def test_chapter_ranges_join_chapters_that_follow_each_other() -> None:
    chosen = [chapter(1, 0, 10), chapter(2, 10, 20), chapter(3, 20, 30)]
    chosen.append(chapter(4, 30, 40))

    assert chapter_ranges(chosen, [3, 2]) == [(10, 30)]
    assert chapter_ranges(chosen, [4, 1]) == [(0, 10), (30, 40)]
    with pytest.raises(ValueError, match="no chapter 7, 9 .1-4."):
        chapter_ranges(chosen, [1, 9, 7])


def test_there_are_no_chapters_before_they_are_made(tmp_path: Path) -> None:
    assert read_chapters(tmp_path) == []


def clip(start: float, end: float, title: str) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "title": title,
        "hook_text": "A hook",
        "description": "About a topic.",
        "hashtags": ["comedy", "topic", "talk"],
        "emphasis_words": ["fridge"],
        "reason": "It is a complete moment.",
        "hook": 80,
        "flow": 75,
        "value": 70,
        "trend": 65,
    }


def ranged(llm: FakeLLMClient, *ranges: tuple[float, float]) -> StepSettings:
    return StepSettings(
        source="unused",
        processing=ProcessingSettings(
            length_presets=["custom"], custom_length_min_s=10, custom_length_max_s=40
        ),
        cfg=CFG,
        llm=llm,
        ranges=ranges,
    )


def titles(job: Path) -> list[str]:
    result = CandidateList.model_validate_json((job / CANDIDATES).read_bytes())
    return [c.title for c in result.clips]


def test_curate_asks_only_about_the_chosen_range_and_keeps_clips_inside(
    job: Path,
) -> None:
    llm = FakeLLMClient(
        json.dumps(
            {
                "clips": [
                    clip(17.0, 30.0, "Inside"),
                    clip(5.0, 20.0, "Starts before the range"),
                    clip(30.0, 40.0, "Ends after the range"),
                ]
            }
        )
    )

    curate.run(job, ranged(llm, (16.9, 35.8)))

    [(_, user)] = llm.calls
    assert "[00:16.9-00:19.7]" in user and "[00:27.6" in user
    assert "Hi everyone." not in user and "My car has" not in user
    assert titles(job) == ["Inside"]


def test_curate_asks_each_range_apart_and_ranks_all_clips_together(
    job: Path,
) -> None:
    llm = FakeLLMClient(
        json.dumps({"clips": [clip(1.0, 14.0, "Yoga clip")]}),
        json.dumps({"clips": [clip(36.0, 50.0, "Car clip")]}),
    )

    curate.run(job, ranged(llm, (35.8, 60.0), (0.5, 16.9)))

    first, second = (user for _, user in llm.calls)
    assert "Hi everyone." in first and "My car has" not in first
    assert "My car has" in second and "Hi everyone." not in second
    assert sorted(titles(job)) == ["Car clip", "Yoga clip"]


def test_a_range_outside_the_timeframe_asks_nothing(job: Path) -> None:
    write_json(job / META, source_meta(start=0.0, end=30.0, duration=60.0))
    llm = FakeLLMClient()

    curate.run(job, ranged(llm, (40.0, 50.0)))

    assert llm.calls == []
    assert titles(job) == []
