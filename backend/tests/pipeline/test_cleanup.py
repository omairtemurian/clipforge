"""Tests of speech cleanup (SPEC-v2 3.5): filler lists per language, the
pause threshold, bad takes from the LLM (mocked) and a preview whose
checked items apply as cut ranges."""

import json

from builders import FIXTURE_LAUGHS, cleanup_item, make_clip, said
from clipforge.captions_templates import read_yaml
from clipforge.fillers import (
    FILLERS_DIR,
    FillerList,
    filler_key,
    filler_languages,
    filler_words,
    list_language,
)
from clipforge.languages import WHISPER_LANGUAGES
from clipforge.models import CleanupOptions, CleanupSuggestion, Transcript
from clipforge.pipeline.cleanup import checked_items, cleanup_cuts, cleanup_preview
from clipforge.pipeline.step import TRANSCRIPT
from fakes import FIXTURES

FIXTURE = Transcript.model_validate_json((FIXTURES / TRANSCRIPT).read_bytes())
CLIP_A = make_clip("karaoke_bold", start=0.5, end=34.35)
NO_PAUSES = CleanupOptions(pauses=False)


def in_language(transcript: Transcript, language: str) -> Transcript:
    """Return transcript as if Whisper had heard language."""
    return transcript.model_copy(update={"language": language})


def preview_of(
    transcript: Transcript, options: CleanupOptions = NO_PAUSES
) -> list[CleanupSuggestion]:
    """Return the preview items of a clip of all of transcript's words."""
    words = transcript.segments[0].words
    clip = make_clip("karaoke_bold", start=words[0].start, end=words[-1].end)
    return cleanup_preview(transcript, [], clip, options).items


def takes(*picks: tuple[int, int]) -> str:
    """Return an LLM reply with the bad takes picks (first, last)."""
    return json.dumps({"takes": [{"first": f, "last": la} for f, la in picks]})


# Filler lists per language


def test_every_filler_list_is_valid_and_named_after_a_whisper_language() -> None:
    codes = filler_languages()

    assert {"en", "es", "fr", "de", "it", "pt", "nl", "ru", "pl", "tr", "fa", "ar"} <= (
        set(codes)
    )
    for code in codes:
        assert code in WHISPER_LANGUAGES
        FillerList.model_validate(read_yaml(FILLERS_DIR / f"{code}.yaml"))
        words = filler_words(code)
        assert words.always and not words.always & words.alone


def test_a_language_uses_its_own_list_or_else_the_english_one() -> None:
    assert [list_language(code) for code in ("es", "pt_BR", "FR-ca", "ja", "")] == [
        "es",
        "pt",
        "fr",
        "en",
        "en",
    ]
    assert "no" in filler_words("pl").alone


def test_spanish_fillers_are_cut_and_este_only_when_it_stands_alone() -> None:
    spanish = in_language(
        said(
            ("Eh,", 1.0, 1.3),
            (" creo", 1.4, 1.7),
            (" que", 1.75, 1.9),
            (" este", 1.95, 2.2),
            (" libro", 2.25, 2.6),
            (" este...", 3.2, 3.5),
            (" es", 4.1, 4.3),
            (" bueno.", 4.35, 4.7),
        ),
        "es",
    )

    assert preview_of(spanish) == [
        cleanup_item(1.0, 1.3, "filler", "eh"),
        cleanup_item(3.2, 3.5, "filler", "este"),
    ]
    assert preview_of(in_language(spanish, "en")) == []


def test_the_english_um_is_a_word_in_german() -> None:
    meeting = said(
        ("Wir", 1.0, 1.2),
        (" treffen", 1.25, 1.6),
        (" uns", 1.65, 1.8),
        (" um", 1.85, 2.0),
        (" acht.", 2.05, 2.4),
    )

    assert preview_of(in_language(meeting, "de")) == []
    assert preview_of(meeting) == [cleanup_item(1.85, 2.0, "filler", "um")]


def test_drawn_out_fillers_match_their_entry_in_any_script() -> None:
    assert filler_key("Ummmmm,") == "umm"
    persian = in_language(
        said(("اممممم", 1.0, 1.5), (" سلام", 1.6, 2.0), (" دوستان", 2.05, 2.5)), "fa"
    )

    assert preview_of(persian) == [cleanup_item(1.0, 1.5, "filler", "امم")]
    assert preview_of(said(("Ummmm", 1.0, 1.4), (" yes", 1.5, 1.8))) == [
        cleanup_item(1.0, 1.4, "filler", "umm")
    ]


def test_extra_fillers_and_a_chosen_language_override_the_transcripts() -> None:
    options = CleanupOptions(pauses=False, language="de", extra_fillers=[" So "])

    preview = cleanup_preview(FIXTURE, [], CLIP_A, options)

    assert preview.filler_language == "de"
    assert [(i.start, i.text) for i in preview.items] == [(1.53, "so"), (7.7, "so")]


def test_fillers_off_finds_only_pauses() -> None:
    options = CleanupOptions(fillers=False)

    items = cleanup_preview(FIXTURE, [], CLIP_A, options).items

    assert {i.kind for i in items} == {"pause"}
    assert (13.65, 16.75) in [(i.start, i.end) for i in items]


# Pause threshold


def test_the_pause_threshold_decides_which_gaps_are_pauses() -> None:
    def spans(threshold: float) -> list[tuple[float, float, str]]:
        options = CleanupOptions(pause_threshold_s=threshold)
        items = cleanup_preview(FIXTURE, [], CLIP_A, options).items
        return [(i.start, i.end, i.kind) for i in items]

    assert spans(0.6) == [
        (6.2, 7.55, "filler"),
        (13.65, 16.75, "pause"),
        (22.6, 24.15, "filler"),
        (33.0, 34.2, "pause"),
    ]
    assert spans(2.0) == [
        (6.75, 7.15, "filler"),
        (13.65, 16.75, "pause"),
        (23.25, 23.6, "filler"),
    ]
    assert spans(5.0) == [(6.75, 7.15, "filler"), (23.25, 23.6, "filler")]


def test_pauses_off_and_laughs_keep_their_gaps() -> None:
    off = cleanup_preview(FIXTURE, [], CLIP_A, NO_PAUSES).items
    laughs = cleanup_preview(FIXTURE, FIXTURE_LAUGHS, CLIP_A, CleanupOptions()).items

    assert [i.kind for i in off] == ["filler", "filler"]
    assert [(i.start, i.end) for i in laughs] == [(6.2, 7.55), (22.6, 24.15)]


def test_each_section_is_cleaned_on_its_own() -> None:
    clip = make_clip("karaoke_bold", segments=[(20.25, 34.35), (0.5, 9.0)])

    items = cleanup_preview(FIXTURE, [], clip, CleanupOptions()).items

    assert [(i.start, i.end, i.kind) for i in items] == [
        (6.2, 7.55, "filler"),
        (22.6, 24.15, "filler"),
        (33.0, 34.2, "pause"),
    ]


# Preview, per-item uncheck and apply


def test_the_preview_adds_bad_takes_in_order_and_leaves_out_applied_items() -> None:
    clip = CLIP_A.model_copy(update={"cut_ranges": [(6.0, 7.6)]})
    bad = cleanup_item(17.25, 19.24, "bad_take", "I bought one of those smart")

    preview = cleanup_preview(FIXTURE, FIXTURE_LAUGHS, clip, CleanupOptions(), [bad])

    assert preview.items == [bad, cleanup_item(22.6, 24.15, "filler", "like")]


def test_apply_cuts_the_checked_items_merged_with_the_clips_cuts() -> None:
    clip = CLIP_A.model_copy(update={"cut_ranges": [(30.0, 30.5)]})
    items = cleanup_preview(FIXTURE, [], clip, CleanupOptions()).items

    assert cleanup_cuts(clip, items) == [
        (6.2, 7.55),
        (13.65, 16.75),
        (22.6, 24.15),
        (30.0, 30.5),
        (33.0, 34.2),
    ]
    assert cleanup_cuts(clip, items, [1, 3]) == [
        (6.2, 7.55),
        (22.6, 24.15),
        (30.0, 30.5),
    ]
    assert cleanup_cuts(clip, items, range(len(items))) == [(30.0, 30.5)]


def test_unchecking_one_of_two_overlapping_items_keeps_only_the_other() -> None:
    clip = make_clip("karaoke_bold", start=1.0, end=4.0)
    items = [
        cleanup_item(1.3, 2.3, "bad_take", "the best way,"),
        cleanup_item(2.0, 2.5, "pause"),
    ]

    assert cleanup_cuts(clip, items) == [(1.3, 2.5)]
    assert cleanup_cuts(clip, items, [0]) == [(2.0, 2.5)]
    assert checked_items(items, [1]) == items[:1]


def test_applied_cuts_stay_inside_the_clips_sections() -> None:
    clip = make_clip("karaoke_bold", segments=[(20.0, 30.0), (0.5, 10.0)])
    items = [cleanup_item(9.5, 21.0, "pause"), cleanup_item(12.0, 13.0, "pause")]

    assert cleanup_cuts(clip, items) == [(9.5, 10.0), (20.0, 21.0)]
