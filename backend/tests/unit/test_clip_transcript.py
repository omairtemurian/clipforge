"""Tests of the words a clip editor shows (clip_transcript)."""

from builders import make_clip
from clipforge.clip_transcript import clip_transcript, context_window, editor_words
from clipforge.models import Segment, Transcript, Word


def word(text: str, start: float, end: float, prob: float = 0.9) -> Word:
    """Return a word of speaker S0."""
    return Word(text=text, start=start, end=end, speaker="S0", prob=prob)


def transcript(*segments: tuple[str, list[Word]]) -> Transcript:
    """Return a transcript of segments given as (text, words)."""
    return Transcript(
        language="en",
        duration=60.0,
        segments=[
            Segment(
                id=index,
                start=words[0].start,
                end=words[-1].end,
                text=text,
                words=words,
                speaker="S0",
            )
            for index, (text, words) in enumerate(segments)
        ],
    )


def test_editor_words_join_the_pieces_of_a_segments_text() -> None:
    words = [
        word(" I", 1.0, 1.2),
        word(" am", 1.2, 1.4),
        word(" twenty", 1.5, 1.8, 0.8),
        word("-five.", 1.8, 2.1, 0.6),
        word(" ", 2.1, 2.2),
    ]
    result = list(editor_words(transcript(("I am twenty-five.", words))))

    assert [(w.text, w.start, w.end, w.prob) for w in result] == [
        ("I", 1.0, 1.2, 0.9),
        ("am", 1.2, 1.4, 0.9),
        ("twenty-five.", 1.5, 2.1, 0.6),
    ]


def test_editor_words_keep_each_word_if_they_do_not_spell_the_text() -> None:
    words = [word("Hello", 0.0, 0.4), word("there", 0.5, 0.9)]
    result = editor_words(transcript(("Hi there", words)))

    assert [w.text for w in result] == ["Hello", "there"]


def test_context_window_stays_inside_the_video() -> None:
    clip = make_clip("minimal", start=10.0, end=40.0)

    assert context_window(clip, 60.0) == (0.0, 60.0)
    assert context_window(clip, 0.0) == (0.0, 70.0)
    assert context_window(clip, 120.0, 5.0) == (5.0, 45.0)
    assert context_window(make_clip("minimal", start=50.0, end=58.0), 55.0) == (
        20.0,
        58.0,
    )


def test_clip_transcript_has_the_words_that_start_in_the_window() -> None:
    words = [word(f"w{t}", float(t), t + 0.5) for t in range(0, 20)]
    text = " ".join(w.text for w in words)
    clip = make_clip("minimal", start=8.0, end=10.0)

    result = clip_transcript(transcript((text, words)), clip, 60.0, 3.0)

    assert [w.start for w in result] == [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]
