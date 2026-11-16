"""Tests of polish.cleanup_suggestions: the speech cleanup the editor reviews."""

from builders import FIXTURE_LAUGHS, word
from clipforge.models import CleanupSuggestion, Segment, Transcript
from clipforge.pipeline.polish import cleanup_suggestions, filler_cuts
from clipforge.pipeline.step import TRANSCRIPT
from fakes import FIXTURES

FIXTURE = Transcript.model_validate_json((FIXTURES / TRANSCRIPT).read_bytes())
CLIP_A = (0.5, 34.35)
TIMED = [("So", 1.0, 1.2), (" um,", 1.3, 1.5), (" uh,", 1.6, 1.8), (" yes.", 1.9, 2.2)]


def suggestion(start: float, end: float, text: str = "") -> CleanupSuggestion:
    """Return a suggestion of a filler cut with text, or of a pause."""
    kind = "filler" if text else "pause"
    return CleanupSuggestion(start=start, end=end, kind=kind, text=text)


def test_suggestions_say_what_each_filler_cut_removes() -> None:
    assert cleanup_suggestions(FIXTURE, FIXTURE_LAUGHS, *CLIP_A) == [
        suggestion(6.2, 7.55, "um"),
        suggestion(22.6, 24.15, "like"),
    ]


def test_without_laughs_the_laugh_gaps_are_suggested_as_pauses() -> None:
    assert cleanup_suggestions(FIXTURE, [], *CLIP_A) == [
        suggestion(6.2, 7.55, "um"),
        suggestion(13.65, 16.75),
        suggestion(22.6, 24.15, "like"),
        suggestion(33.0, 34.2),
    ]


def test_filler_cuts_are_the_spans_of_the_suggestions() -> None:
    for events in ((), FIXTURE_LAUGHS):
        spans = [
            (s.start, s.end) for s in cleanup_suggestions(FIXTURE, events, *CLIP_A)
        ]
        assert filler_cuts(FIXTURE, events, *CLIP_A) == spans


def test_fillers_in_one_gap_are_one_suggestion() -> None:
    words = [word(*timed) for timed in TIMED]
    spoken = Segment(
        id=0, start=1.0, end=2.2, text="So um, uh, yes.", words=words, speaker="S0"
    )
    transcript = Transcript(language="en", duration=3.0, segments=[spoken])

    assert cleanup_suggestions(transcript, [], 1.0, 2.2) == [
        suggestion(1.3, 1.8, "um uh")
    ]
