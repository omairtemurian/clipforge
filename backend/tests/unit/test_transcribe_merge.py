"""Tests for the pure chunk planning, merging and sentence grouping of transcribe.

Chunk outputs are synthetic Whisper words (chunk-relative times, leading
spaces as Whisper writes them); each test checks the exact merged words.
"""

from collections.abc import Sequence

import pytest
from clipforge.models import Segment, Transcript, Word
from clipforge.pipeline.transcript_merge import (
    MAX_SENTENCE_S,
    Chunk,
    TimedWord,
    build_transcript,
    merge_chunks,
    plan_chunks,
    to_source_time,
)

Row = tuple[str, float, float]


def tw(text: str, start: float, end: float, *, last: bool = False) -> TimedWord:
    """A Whisper word with a leading space, probability 0.9."""
    return TimedWord(f" {text}", start, end, 0.9, segment_end=last)


def shifted(offset: float, *rows: Row) -> list[TimedWord]:
    """Words given in source time, as Whisper reports them in a chunk at offset."""
    return [tw(text, start - offset, end - offset) for text, start, end in rows]


def rows(words: Sequence[TimedWord]) -> list[Row]:
    """The text and times (to the millisecond) of words."""
    return [(w.text.strip(), round(w.start, 3), round(w.end, 3)) for w in words]


def test_plan_chunks_covers_the_range_with_overlapping_chunks() -> None:
    assert plan_chunks(0, 1500, 600, 60) == [
        Chunk(0, 600),
        Chunk(540, 1140),
        Chunk(1080, 1500),
    ]
    assert plan_chunks(0, 1140, 600, 60) == [Chunk(0, 600), Chunk(540, 1140)]
    assert plan_chunks(12.5, 70, 600, 60) == [Chunk(12.5, 70)]
    assert plan_chunks(30, 150, 60, 0) == [Chunk(30, 90), Chunk(90, 150)]


@pytest.mark.parametrize(
    ("start", "end", "length", "overlap", "message"),
    [
        (10, 10, 600, 60, "nothing to transcribe"),
        (0, 100, 60, 60, "must be >= 0 and shorter than the chunk"),
        (0, 100, 60, -1, "must be >= 0 and shorter than the chunk"),
    ],
)
def test_plan_chunks_rejects_bad_ranges(
    start: float, end: float, length: float, overlap: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        plan_chunks(start, end, length, overlap)


def test_to_source_time_offsets_and_clamps_to_the_chunk() -> None:
    words = [tw("first", 0.5, 1.0), tw("last", 599.5, 600.4)]
    assert rows(to_source_time(Chunk(540, 1140), words)) == [
        ("first", 540.5, 541.0),
        ("last", 1139.5, 1140.0),
    ]


def test_merge_of_one_chunk_moves_its_words_to_source_time() -> None:
    words = [tw("Hello", 0.0, 0.4), tw("there.", 0.5, 0.9, last=True)]
    merged = merge_chunks([(Chunk(30, 90), words)])
    assert rows(merged) == [("Hello", 30.0, 30.4), ("there.", 30.5, 30.9)]
    assert merged[-1].segment_end


def test_merge_keeps_each_word_of_an_identical_overlap_once() -> None:
    first = shifted(
        0,
        ("Hello", 1.0, 1.4), ("world.", 1.5, 2.0), ("This", 7.0, 7.3),
        ("is", 7.4, 7.5), ("a", 7.6, 7.7), ("test.", 8.0, 8.5), ("And", 9.6, 9.9),
    )  # fmt: skip
    second = shifted(
        6,
        ("This", 7.0, 7.3), ("is", 7.4, 7.5), ("a", 7.6, 7.7), ("test.", 8.0, 8.5),
        ("And", 9.6, 9.9), ("more", 10.0, 10.3), ("words.", 10.4, 11.0),
    )  # fmt: skip
    merged = merge_chunks([(Chunk(0, 10), first), (Chunk(6, 16), second)])
    assert rows(merged) == [
        ("Hello", 1.0, 1.4), ("world.", 1.5, 2.0), ("This", 7.0, 7.3),
        ("is", 7.4, 7.5), ("a", 7.6, 7.7), ("test.", 8.0, 8.5), ("And", 9.6, 9.9),
        ("more", 10.0, 10.3), ("words.", 10.4, 11.0),
    ]  # fmt: skip


def test_merge_splices_jittered_chunks_and_drops_their_cut_off_edges() -> None:
    # The first chunk ends inside "And" and the second starts inside "This".
    first = shifted(
        0,
        ("So", 5.0, 5.3), ("This", 7.0, 7.3), ("is", 7.4, 7.5), ("a", 7.6, 7.7),
        ("test,", 8.0, 8.5), ("an", 9.8, 10.0),
    )  # fmt: skip
    second = shifted(
        6,
        ("his", 6.0, 6.3), ("is", 7.45, 7.55), ("a", 7.62, 7.72),
        ("Test.", 8.03, 8.52), ("And", 9.62, 9.92), ("more.", 10.0, 10.4),
    )  # fmt: skip
    merged = merge_chunks([(Chunk(0, 10), first), (Chunk(6, 16), second)])
    assert rows(merged) == [
        ("So", 5.0, 5.3), ("This", 7.0, 7.3), ("is", 7.4, 7.5), ("a", 7.6, 7.7),
        ("Test.", 8.03, 8.52), ("And", 9.62, 9.92), ("more.", 10.0, 10.4),
    ]  # fmt: skip


def test_merge_pairs_a_repeated_word_with_its_own_occurrence() -> None:
    # The overlap's middle is 7.85: nearest to pairs of different "no"s
    # (7.7 with 8.02, or 8.0 with 7.72), which would lose or repeat one.
    words = [("no", 7.7, 7.9), ("no", 8.0, 8.2), ("no.", 8.3, 8.5)]
    later = [("no", 7.72, 7.9), ("no", 8.02, 8.2), ("no.", 8.32, 8.5)]
    merged = merge_chunks(
        [(Chunk(0, 10), shifted(0, *words)), (Chunk(5.7, 15.7), shifted(5.7, *later))]
    )
    assert rows(merged) == [("no", 7.72, 7.9), ("no", 8.02, 8.2), ("no.", 8.32, 8.5)]


def test_merge_without_a_common_word_cuts_the_overlap_at_its_middle() -> None:
    first = shifted(0, ("One.", 1.0, 1.5), ("Two.", 6.5, 7.0), ("Hi", 7.9, 8.3))
    second = shifted(6, ("Hey", 7.95, 8.3), ("Three.", 9.0, 9.5))
    merged = merge_chunks([(Chunk(0, 10), first), (Chunk(6, 16), second)])
    assert rows(merged) == [
        ("One.", 1.0, 1.5),
        ("Two.", 6.5, 7.0),
        ("Hey", 7.95, 8.3),
        ("Three.", 9.0, 9.5),
    ]


def test_merge_keeps_overlap_words_that_only_one_chunk_heard() -> None:
    first = shifted(0, ("Start.", 1.0, 1.5), ("late", 8.5, 9.0), ("words.", 9.1, 9.6))
    third = shifted(12, ("Quiet", 12.5, 12.9), ("End.", 17.0, 17.5))
    merged = merge_chunks(
        [(Chunk(0, 10), first), (Chunk(6, 16), []), (Chunk(12, 20), third)]
    )
    assert rows(merged) == [
        ("Start.", 1.0, 1.5),
        ("late", 8.5, 9.0),
        ("words.", 9.1, 9.6),
        ("Quiet", 12.5, 12.9),
        ("End.", 17.0, 17.5),
    ]


def test_merge_splices_three_chunks() -> None:
    def chunk_words(offset: float) -> list[TimedWord]:
        everything = [(f"w{i}", float(i), i + 0.5) for i in range(20)]
        inside = [r for r in everything if offset <= r[1] and r[2] <= offset + 10]
        return shifted(offset, *inside)

    chunks = [Chunk(0, 10), Chunk(6, 16), Chunk(12, 20)]
    merged = merge_chunks([(chunk, chunk_words(chunk.start)) for chunk in chunks])
    assert rows(merged) == [(f"w{i}", float(i), i + 0.5) for i in range(20)]


def test_merge_never_lets_word_times_go_back_or_overlap() -> None:
    words = [tw("a", 1.0, 1.6), tw("b", 1.5, 2.0), tw("c", 1.8, 1.7), tw("d", 1.7, 2.5)]
    assert rows(merge_chunks([(Chunk(0, 60), words)])) == [
        ("a", 1.0, 1.5),
        ("b", 1.5, 1.8),
        ("c", 1.8, 1.8),
        ("d", 1.8, 2.5),
    ]


def test_merge_of_no_words_is_empty() -> None:
    assert merge_chunks([(Chunk(0, 10), []), (Chunk(6, 16), [])]) == []
    assert merge_chunks([]) == []


def word(text: str, start: float, end: float, prob: float = 0.9) -> Word:
    return Word(text=text, start=start, end=end, speaker="S0", prob=prob)


def test_build_transcript_groups_words_into_sentences() -> None:
    words = [
        tw("Hi", 0.5, 0.75), tw("everyone.", 0.79, 1.41),
        tw("So,", 1.53, 1.78), tw("I", 1.8, 1.9), tw("tried", 1.95, 2.3),
        TimedWord(" yoga.", 2.4, 2.9, 0.98765),
    ]  # fmt: skip
    transcript = build_transcript(words, language="en", duration=60.0)
    first = [word("Hi", 0.5, 0.75), word("everyone.", 0.79, 1.41)]
    second = [
        word("So,", 1.53, 1.78), word("I", 1.8, 1.9), word("tried", 1.95, 2.3),
        word("yoga.", 2.4, 2.9, prob=0.988),
    ]  # fmt: skip
    assert transcript == Transcript(
        language="en",
        duration=60.0,
        segments=[
            Segment(
                id=0, start=0.5, end=1.41, text="Hi everyone.", words=first,
                speaker="S0",
            ),
            Segment(
                id=1, start=1.53, end=2.9, text="So, I tried yoga.", words=second,
                speaker="S0",
            ),
        ],
    )  # fmt: skip


def test_build_transcript_sentence_ends() -> None:
    texts = [
        "Really?", "Mr.", "Smith", "said", '"stop!"', "Then", "e.g.", "this",
        "(quietly).", "And", "so...", "Yes", "100%!",
    ]  # fmt: skip
    words = [tw(text, i, i + 0.5) for i, text in enumerate(texts)]
    transcript = build_transcript(words, language="en", duration=20.0)
    assert [s.text for s in transcript.segments] == [
        "Really?",
        'Mr. Smith said "stop!"',
        "Then e.g. this (quietly).",
        "And so...",
        "Yes 100%!",
    ]
    assert [s.id for s in transcript.segments] == [0, 1, 2, 3, 4]


def test_build_transcript_cuts_unpunctuated_speech_at_whisper_segments() -> None:
    # One word a second; Whisper segments end every 8 words.
    words = [tw(f"w{i}", i, i + 0.5, last=i % 8 == 7) for i in range(40)]
    transcript = build_transcript(words, language="en", duration=40.0)
    spans = [(s.start, s.end) for s in transcript.segments]
    assert spans == [(0.0, 23.5), (24.0, 39.5)]
    assert spans[0][1] - spans[0][0] >= MAX_SENTENCE_S


def test_build_transcript_keeps_whisper_spacing_and_skips_blank_words() -> None:
    words = [
        TimedWord("你好", 1.0, 1.4, 0.9),
        TimedWord(" ", 1.4, 1.5, 0.1),
        TimedWord("世界。", 1.5, 2.0, 0.9),
    ]
    transcript = build_transcript(words, language="zh", duration=3.0)
    [segment] = transcript.segments
    assert segment.text == "你好世界。"
    assert [w.text for w in segment.words] == ["你好", "世界。"]
    assert build_transcript([], language="en", duration=5.0) == Transcript(
        language="en", duration=5.0, segments=[]
    )


def test_merged_chunks_round_trip_as_a_strict_transcript() -> None:
    first = shifted(0, ("Hello", 1.0, 1.4), ("there.", 8.0, 8.5))
    second = shifted(6, ("there.", 8.01, 8.5), ("Bye.", 12.0, 12.4))
    words = merge_chunks([(Chunk(0, 10), first), (Chunk(6, 16), second)])
    transcript = build_transcript(words, language="en", duration=16.0)
    data = transcript.model_dump_json()
    assert Transcript.model_validate_json(data, strict=True) == transcript
    assert [s.text for s in transcript.segments] == ["Hello there.", "Bye."]
