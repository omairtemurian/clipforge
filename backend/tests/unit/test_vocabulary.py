"""Tests of the brand vocabulary (SPEC-v2 3.4): its model, its file, the
hotwords, the corrections of a transcript, and replace-everywhere on a
project's transcript and clips."""

import json
from pathlib import Path

import pytest
from builders import said, word
from clipforge import vocabulary
from clipforge.config import Settings
from clipforge.db import ClipRow
from clipforge.models import Segment, Transcript, Vocabulary
from clipforge.pipeline.enrich import piece_words
from clipforge.pipeline.transcript_correct import (
    correct_transcript,
    correct_word,
    replace_text,
)
from clipforge.vocabulary import (
    HOTWORDS_MAX_CHARS,
    VocabularyError,
    hotwords_text,
    load_vocabulary,
    save_vocabulary,
)
from fakes import FIXTURES
from pydantic import ValidationError
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


def texts(transcript: Transcript) -> list[tuple[str, list[str]]]:
    """Each segment's text and the texts of its words."""
    return [(s.text, [w.text for w in s.words]) for s in transcript.segments]


def test_vocabulary_phrases_are_tidied_and_terms_kept_once() -> None:
    v = Vocabulary(
        terms=["  Kubernetes ", "kubernetes", "Open   AI"],
        corrections={"open  ai": " OpenAI "},
    )
    assert v.terms == ["Kubernetes", "Open AI"]
    assert v.corrections == {"open ai": "OpenAI"}


@pytest.mark.parametrize(
    "data",
    [
        {"terms": [""]},
        {"terms": ["- -"]},
        {"corrections": {"ai": ""}},
        {"corrections": {"AI": "OpenAI", "ai": "Open AI"}},
        {"terms": ["x" * 101]},
        {"terms": [f"t{n}" for n in range(101)]},
    ],
)
def test_invalid_vocabularies_are_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Vocabulary.model_validate(data)


def test_the_vocabulary_is_saved_in_the_data_directory(tmp_path: Path) -> None:
    cfg = Settings(data_dir=tmp_path / "data")
    assert load_vocabulary(cfg) == Vocabulary()

    saved = Vocabulary(terms=["Kubernetes"], corrections={"cuber netes": "Kubernetes"})
    save_vocabulary(saved, cfg)

    assert load_vocabulary(cfg) == saved
    assert json.loads((tmp_path / "data" / "vocabulary.json").read_text()) == {
        "terms": ["Kubernetes"],
        "corrections": {"cuber netes": "Kubernetes"},
    }


def test_a_broken_vocabulary_file_is_an_error(tmp_path: Path) -> None:
    cfg = Settings(data_dir=tmp_path)
    (tmp_path / "vocabulary.json").write_text('{"terms": [1]}')
    with pytest.raises(VocabularyError, match="is not a valid vocabulary"):
        load_vocabulary(cfg)


def test_terms_are_the_hotwords_up_to_a_length() -> None:
    assert hotwords_text(Vocabulary()) is None
    assert hotwords_text(Vocabulary(terms=["Kubernetes", "OpenAI"])) == (
        "Kubernetes, OpenAI"
    )
    long = Vocabulary(terms=[f"{'w' * 50}{n:02d}" for n in range(40)])
    cut = hotwords_text(long)
    assert cut is not None and len(cut) <= HOTWORDS_MAX_CHARS
    assert cut.split(", ") == long.terms[: len(cut.split(", "))]
    assert len(cut.split(", ")) < 40


def test_a_correction_keeps_the_punctuation_and_the_time_of_the_word() -> None:
    transcript = said(("Try", 0, 0.2), ("open", 1, 1.2), ("AI,", 1.3, 1.6))

    fixed, count = correct_transcript(transcript, {"Open AI": "OpenAI"})

    assert count == 1
    [segment] = fixed.segments
    assert (segment.text, [w.text for w in segment.words]) == (
        "Try OpenAI,",
        ["Try", "OpenAI,"],
    )
    assert (segment.words[1].start, segment.words[1].end) == (1, 1.6)
    assert (segment.start, segment.end) == (0, 1.6)
    assert segment.words[1].prob == 0.9 and segment.words[1].speaker == "S0"
    assert piece_words(segment) is not None
    assert texts(transcript)[0][0] == "Try open AI,"


def test_a_word_that_whisper_split_is_one_piece() -> None:
    words = [word("Kuber", 1, 1.3), word("netes.", 1.3, 1.8)]
    transcript = Transcript(
        language="en",
        duration=5,
        segments=[
            Segment(
                id=0, start=1, end=1.8, text="Kubernetes.", words=words, speaker="S0"
            )
        ],
    )

    fixed, count = correct_transcript(transcript, {"kubernetes": "K8s"})

    assert count == 1
    assert texts(fixed) == [("K8s.", ["K8s."])]
    assert (fixed.segments[0].words[0].start, fixed.segments[0].words[0].end) == (
        1,
        1.8,
    )


def test_a_longer_replacement_spreads_its_words_over_the_time() -> None:
    transcript = said(("ok", 0, 0.2), ("yoga.", 2, 3))

    fixed, _ = correct_transcript(transcript, {"yoga": "Yoga Flow Pro"})

    [segment] = fixed.segments
    assert segment.text == "ok Yoga Flow Pro."
    assert [(w.text, w.start, w.end) for w in segment.words[1:]] == [
        ("Yoga", 2, 2.333),
        ("Flow", 2.333, 2.667),
        ("Pro.", 2.667, 3),
    ]
    assert piece_words(segment) is not None


def test_only_whole_words_match_and_the_longest_correction_wins() -> None:
    transcript = said(
        ("he", 0, 0.2), ("said", 0.3, 0.5), ("ai", 0.6, 0.8), ("tech", 1, 1.2)
    )

    fixed, count = correct_transcript(transcript, {"ai": "AI", "ai tech": "AI Tech Co"})

    assert count == 1
    assert texts(fixed) == [("he said AI Tech Co", ["he", "said", "AI", "Tech", "Co"])]


def test_unchanged_transcripts_are_returned_as_they_are() -> None:
    transcript = said(("OpenAI", 0, 0.2), ("rocks", 0.3, 0.5))
    assert correct_transcript(transcript, {"openai": "OpenAI"}) == (transcript, 0)
    assert correct_transcript(transcript, {}) == (transcript, 0)
    assert correct_transcript(transcript, {"zzz": "Y"}) == (transcript, 0)


def test_segments_whose_words_do_not_spell_the_text_are_corrected_per_word() -> None:
    words = [word("open", 0, 0.2), word("ai", 0.3, 0.5)]
    odd = Segment(
        id=0, start=0, end=0.5, text="something else", words=words, speaker="S0"
    )
    transcript = Transcript(language="en", duration=1, segments=[odd])

    fixed, count = correct_transcript(transcript, {"open ai": "OpenAI"})

    assert count == 1
    assert texts(fixed) == [("OpenAI", ["OpenAI"])]


def test_fixture_transcript_is_corrected_everywhere_it_says_the_word() -> None:
    transcript = Transcript.model_validate_json(
        (FIXTURES / "transcript.json").read_text()
    )

    fixed, count = correct_transcript(transcript, {"fridges": "Fridges (tm)"})

    assert count == 1
    [segment] = [s for s in fixed.segments if "Fridges" in s.text]
    assert segment.text == "Then I bought one of those smart Fridges (tm)."
    assert len(fixed.segments) == len(transcript.segments)


def test_replace_text_changes_whole_words_in_any_case() -> None:
    assert replace_text("Open AI and open   ai, not Open AIs", "open ai", "OpenAI") == (
        "OpenAI and OpenAI, not Open AIs",
        2,
    )
    assert replace_text("a.b (c+) c+", "c+", "D") == ("a.b (D) D", 2)
    assert replace_text("nothing", "x", "y") == ("nothing", 0)


def test_a_caption_word_is_corrected_only_when_it_is_the_one_word() -> None:
    assert correct_word("Pizza.", "pizza", "Pie") == "Pie."
    assert correct_word("Pie.", "pie", "Pie") is None
    assert correct_word("pizzas", "pizza", "Pie") is None
    assert correct_word("open", "open ai", "OpenAI") is None


def seed_project(engine: Engine, sample_mp4: Path) -> tuple[int, Path]:
    """Add a project with the fixture transcript."""
    project_id = add_project(engine)
    return project_id, add_work(engine, project_id, sample_mp4)


def test_replace_everywhere_changes_the_transcript_and_all_the_clips(
    data_dir: Path, sample_mp4: Path, engine: Engine
) -> None:
    project_id, work = seed_project(engine, sample_mp4)
    other_id, other_work = seed_project(engine, sample_mp4)
    first = add_clip(
        engine,
        project_id,
        "candidate",
        80,
        title="Yoga fail",
        hook_text="My YOGA teacher",
        description="I tried yoga. Yogas differ.",
        reason="The yoga part is funny",
        hashtags=["yoga", "funny"],
        emphasis_words=["yoga", "body"],
        caption_overrides=[word("yoga.", 2.53, 2.9), word("pizza.", 10.09, 10.5)],
    )
    second = add_clip(engine, project_id, "rendered", 70, title="no match")
    untouched = add_clip(engine, other_id, "candidate", 60, title="yoga elsewhere")

    result = vocabulary.replace_everywhere(
        engine, project_id, work, "yoga", "Yoga Flow"
    )

    assert (result.transcript_matches, result.clips_changed) == (1, 1)
    transcript = Transcript.model_validate_json((work / "transcript.json").read_text())
    assert "So, I tried Yoga Flow." in [s.text for s in transcript.segments]
    other = Transcript.model_validate_json((other_work / "transcript.json").read_text())
    assert "So, I tried yoga." in [s.text for s in other.segments]
    with Session(engine) as session:
        one = session.get(ClipRow, first)
        two = session.get(ClipRow, second)
        three = session.get(ClipRow, untouched)
        assert one and two and three
        assert one.title == "Yoga Flow fail"
        assert one.hook_text == "My Yoga Flow teacher"
        assert one.description == "I tried Yoga Flow. Yogas differ."
        assert one.reason == "The Yoga Flow part is funny"
        assert one.hashtags == ["YogaFlow", "funny"]
        assert one.emphasis_words == ["Yoga Flow", "body"]
        assert [w.text for w in one.caption_overrides] == ["Yoga Flow.", "pizza."]
        assert two.title == "no match"
        assert three.title == "yoga elsewhere"


def test_replace_everywhere_without_a_work_directory_changes_the_clips(
    data_dir: Path, engine: Engine
) -> None:
    project_id = add_project(engine)
    clip = add_clip(engine, project_id, "candidate", 80, title="Pizza time")

    result = vocabulary.replace_everywhere(engine, project_id, None, "pizza", "Pie")

    assert (result.transcript_matches, result.clips_changed) == (0, 1)
    with Session(engine) as session:
        row = session.get(ClipRow, clip)
        assert row is not None and row.title == "Pie time"
        assert row.hashtags == ["food", "Pie", "funny"]


def test_a_transcript_file_is_written_only_when_something_changed(
    data_dir: Path, sample_mp4: Path, engine: Engine
) -> None:
    project_id, work = seed_project(engine, sample_mp4)
    before = (work / "transcript.json").stat().st_mtime_ns

    result = vocabulary.replace_everywhere(engine, project_id, work, "zzz", "Y")

    assert result.transcript_matches == 0
    assert (work / "transcript.json").stat().st_mtime_ns == before
