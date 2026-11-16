"""Checks the hand-written transcript.json and llm_response.json fixtures.

Unit tests use these files instead of Whisper and the LLM (SPEC 9.1). The
transcript must line up with the speech bursts of sample.mp4 (listed in
expected.json). The LLM response must give curate real work: one
near-duplicate pair for the IoU dedupe and one candidate that the default
length preset drops.
"""

import json
import re
from itertools import combinations, pairwise
from pathlib import Path
from typing import Any

import pytest
from clipforge.candidate_rules import validate_candidate
from clipforge.config import Settings
from clipforge.models import (
    CandidateList,
    ClipCandidate,
    LengthPreset,
    Transcript,
    Word,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
# Pauses the pipeline acts on, in seconds: a caption line break (SPEC 6.9),
# the silence before a snapped clip start (SPEC 6.7), and a removable pause
# (SPEC 6.10).
CAPTION_PAUSE_S = 0.3
SILENCE_S = 0.35
LONG_PAUSE_S = 0.6
# SPEC 4 defaults, set explicitly so that a local config.yaml cannot change them.
DEFAULTS = Settings(clip_min_s=20, clip_max_s=75)

Span = tuple[float, float]


def read(name: str) -> str:
    """Return the text of a file in the fixtures directory."""
    return (FIXTURES / name).read_text()


def norm(text: str) -> str:
    """Lower-case a word and strip its punctuation ("Like," -> "like")."""
    return re.sub(r"[^\w']", "", text).lower()


def pauses(words: list[Word], index: int, duration: float) -> Span:
    """Return the silence before and after words[index], in seconds."""
    word = words[index]
    before = word.start - (words[index - 1].end if index > 0 else 0.0)
    after = (words[index + 1].start if index + 1 < len(words) else duration) - word.end
    return before, after


def llm_average(c: ClipCandidate) -> float:
    """Return the mean of the four LLM scores, which the IoU dedupe compares."""
    return (c.hook + c.flow + c.value + c.trend) / 4


def iou(a: ClipCandidate, b: ClipCandidate) -> float:
    """Return the intersection over union of two candidates' time ranges."""
    overlap = min(a.end, b.end) - max(a.start, b.start)
    return max(overlap, 0.0) / (max(a.end, b.end) - min(a.start, b.start))


@pytest.fixture(scope="module")
def transcript() -> Transcript:
    """transcript.json, parsed strictly; unknown keys are errors."""
    return Transcript.model_validate_json(
        read("transcript.json"), strict=True, extra="forbid"
    )


@pytest.fixture(scope="module")
def words(transcript: Transcript) -> list[Word]:
    """Every word of the transcript, in order."""
    return [word for segment in transcript.segments for word in segment.words]


@pytest.fixture(scope="module")
def speech(expected: dict[str, Any]) -> list[Span]:
    """The (start, end) times of the speech bursts in sample.mp4."""
    return [(burst["start"], burst["end"]) for burst in expected["speech"]]


@pytest.fixture(scope="module")
def candidates() -> list[ClipCandidate]:
    """The clips of llm_response.json, parsed strictly; unknown keys are errors."""
    response = CandidateList.model_validate_json(
        read("llm_response.json"), strict=True, extra="forbid"
    )
    return response.clips


def test_transcript_matches_the_sample_video(
    transcript: Transcript, words: list[Word], expected: dict[str, Any]
) -> None:
    assert transcript.language == "en"
    assert transcript.duration == expected["media"]["duration"] == 60
    # Diarization is off by default, so every word is speaker S0 (SPEC 2).
    assert {segment.speaker for segment in transcript.segments} == {"S0"}
    assert {word.speaker for word in words} == {"S0"}
    assert all(0 < word.prob <= 1 for word in words)


def test_segments_are_numbered_sentences_tight_around_their_words(
    transcript: Transcript,
) -> None:
    segments = transcript.segments
    assert [segment.id for segment in segments] == list(range(len(segments)))
    for segment in segments:
        assert segment.words
        assert segment.start == segment.words[0].start
        assert segment.end == segment.words[-1].end
        assert segment.text == " ".join(word.text for word in segment.words)
        # Segments are sentences: only their last word ends with . ? or !
        ends_sentence = [word.text[-1] in ".?!" for word in segment.words]
        assert ends_sentence == [False] * (len(ends_sentence) - 1) + [True]
    assert all(a.end <= b.start for a, b in pairwise(segments))


def test_words_are_monotonic_non_overlapping_and_inside_their_segment(
    transcript: Transcript, words: list[Word]
) -> None:
    for segment in transcript.segments:
        for word in segment.words:
            assert segment.start <= word.start < word.end <= segment.end, word
    assert all(a.end <= b.start for a, b in pairwise(words))
    for word in words:
        assert word.text and not re.search(r"\s", word.text), word


def test_words_fill_the_speech_bursts_of_sample_mp4(
    words: list[Word], speech: list[Span]
) -> None:
    by_burst: list[list[Word]] = [[] for _ in speech]
    for word in words:
        inside = [
            i for i, (s, e) in enumerate(speech) if s <= word.start < word.end <= e
        ]
        assert len(inside) == 1, word
        by_burst[inside[0]].append(word)
    for (start, end), burst in zip(speech, by_burst, strict=True):
        assert burst, (start, end)
        assert (burst[0].start, burst[-1].end) == (start, end)
        # Real pauses only fall between bursts, where sample.mp4 is silent.
        assert all(b.start - a.end < CAPTION_PAUSE_S for a, b in pairwise(burst))


def test_a_sentence_ends_just_before_each_laugh(
    transcript: Transcript, words: list[Word], expected: dict[str, Any]
) -> None:
    for laugh in expected["laughs"]:
        assert all(w.end <= laugh["start"] or w.start >= laugh["end"] for w in words)
        punchline_end = pytest.approx(laugh["start"] - 0.3)
        assert any(segment.end == punchline_end for segment in transcript.segments)


def test_fillers_um_uh_and_a_standalone_like(
    transcript: Transcript, words: list[Word]
) -> None:
    texts = [norm(word.text) for word in words]
    assert texts.count("um") == texts.count("uh") == 1
    assert texts.count("like") == 2
    gaps = {
        i: pauses(words, i, transcript.duration)
        for i, text in enumerate(texts)
        if text in {"um", "uh", "like"}
    }
    # um, uh and one "like" stand alone between silences; that "like" has
    # pauses longer than 0.6 s on both sides, so any pause threshold agrees.
    standalone = {i: gap for i, gap in gaps.items() if min(gap) >= SILENCE_S}
    assert sorted(texts[i] for i in standalone) == ["like", "uh", "um"]
    like = next(i for i in standalone if texts[i] == "like")
    assert min(standalone[like]) > LONG_PAUSE_S
    # The other "like" sits inside a phrase, so it is not a filler (SPEC 6.10).
    in_phrase = [texts[i] for i, gap in gaps.items() if max(gap) < CAPTION_PAUSE_S]
    assert in_phrase == ["like"]


def test_each_snap_start_rule_has_a_word_only_it_allows(
    transcript: Transcript, words: list[Word]
) -> None:
    """SPEC 6.7 snaps a clip start to a word that begins a segment or follows
    a silence; some words meet only one of the two conditions."""
    segment_starts: set[int] = set()
    index = 0
    for segment in transcript.segments:
        segment_starts.add(index)
        index += len(segment.words)
    after_silence = {
        i
        for i in range(1, len(words))
        if words[i].start - words[i - 1].end >= SILENCE_S
    }
    assert segment_starts - after_silence - {0}
    assert after_silence - segment_starts


def test_llm_response_has_three_or_more_candidates_inside_the_video(
    candidates: list[ClipCandidate], transcript: Transcript
) -> None:
    assert json.loads(read("llm_response.json")).keys() == {"clips"}
    assert len(candidates) >= 3
    assert all(0 <= c.start < c.end <= transcript.duration for c in candidates)


def test_one_pair_overlaps_and_the_weaker_candidate_is_listed_first(
    candidates: list[ClipCandidate],
) -> None:
    overlapping = [(a, b) for a, b in combinations(candidates, 2) if iou(a, b) > 0.5]
    assert len(overlapping) == 1
    first, second = overlapping[0]
    assert iou(first, second) == pytest.approx((32.9 - 1.5) / (35.2 - 0.5))
    # A dedupe that keeps the first of the pair, not the higher LLM average,
    # would keep the weaker cut.
    assert llm_average(first) < llm_average(second)
    averages = [llm_average(c) for c in candidates]
    assert len(set(averages)) == len(averages)


@pytest.mark.parametrize(
    ("preset", "kept"),
    [("auto", [0, 1, 2, 3]), ("lt30", [3, 4]), ("30_60", [0, 1, 2])],
)
def test_length_presets_keep_these_candidates(
    candidates: list[ClipCandidate],
    transcript: Transcript,
    preset: LengthPreset,
    kept: list[int],
) -> None:
    results = [
        validate_candidate(c, transcript.duration, [preset], DEFAULTS)
        for c in candidates
    ]
    assert [i for i, (ok, _) in enumerate(results) if ok] == kept


def test_emphasis_words_are_spoken_inside_their_candidate(
    candidates: list[ClipCandidate], words: list[Word]
) -> None:
    for c in candidates:
        spoken = {norm(w.text) for w in words if c.start <= w.start < w.end <= c.end}
        assert c.emphasis_words
        assert set(c.emphasis_words) <= spoken, c.title
