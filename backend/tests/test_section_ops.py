"""Tests of the section ops of a clip (SPEC-v2 3.5): trim/extend, add a part
of the source, split, delete and rearrange its segments, and how a clip
with sections out of source order plays: the parts its render keeps, its
caption words, its length and its preview key."""

import pytest
from builders import make_clip, plan_at, said
from clipforge.clip_edit import (
    ClipEditError,
    SectionNotFound,
    add_section,
    delete_section,
    edit_problems,
    reorder_sections,
    section_problems,
    split_section,
    trim_section,
)
from clipforge.models import SourceSpan
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.frame_cuts import kept_spans
from clipforge.pipeline.polish import spoken_words
from clipforge.pipeline.sections import (
    fit_cuts,
    played_spans,
    reorder_words,
    section_gaps,
    with_gaps,
)
from clipforge.preview import preview_key
from clipforge.timeline import clip_length, respan, timeline_of

FPS = 30
# Three sections of a 60 s source, in source order, with gaps between them.
SECTIONS: list[SourceSpan] = [(10.0, 12.0), (20.0, 23.0), (30.0, 31.0)]


def test_trim_moves_a_section() -> None:
    assert trim_section(SECTIONS, 1, 21.0, 22.5, 60.0) == [
        (10.0, 12.0),
        (21.0, 22.5),
        (30.0, 31.0),
    ]


def test_extend_clamps_to_the_source() -> None:
    first = trim_section(SECTIONS[:1], 0, 0.0, 99.0, 60.0)
    unknown = trim_section(SECTIONS[:1], 0, 5.0, 99.0, 0.0)

    assert first == [(0.0, 60.0)]
    assert unknown == [(5.0, 99.0)]


def test_extend_clamps_to_the_sections_next_to_it_in_the_source() -> None:
    rearranged = reorder_sections(SECTIONS, [2, 0, 1])

    extended = trim_section(rearranged, 1, 0.0, 25.0, 60.0)

    assert extended == [(30.0, 31.0), (0.0, 20.0), (20.0, 23.0)]


def test_trim_needs_something_of_the_section_left() -> None:
    with pytest.raises(ClipEditError, match="leaves nothing of section 1"):
        trim_section(SECTIONS, 1, 31.0, 40.0, 60.0)
    with pytest.raises(SectionNotFound):
        trim_section(SECTIONS, 3, 1.0, 2.0, 60.0)


def test_add_a_section_from_anywhere_in_the_source() -> None:
    last = add_section(SECTIONS, 40.0, 45.0, 60.0)
    first = add_section(SECTIONS, 0.0, 5.0, 60.0, index=0)
    clamped = add_section(SECTIONS, 50.0, 70.0, 60.0, index=1)

    assert last == [*SECTIONS, (40.0, 45.0)]
    assert first == [(0.0, 5.0), *SECTIONS]
    assert clamped[1] == (50.0, 60.0)


@pytest.mark.parametrize(
    ("start", "end", "index", "message"),
    [
        (11.0, 15.0, None, "overlaps section 0"),
        (5.0, 40.0, None, "overlaps section 0"),
        (60.0, 70.0, None, "not inside the video"),
        (40.0, 45.0, 4, "after the clip's 3 sections"),
    ],
)
def test_an_added_section_may_not_overlap(
    start: float, end: float, index: int | None, message: str
) -> None:
    with pytest.raises(ClipEditError, match=message):
        add_section(SECTIONS, start, end, 60.0, index)


def test_split_a_section_at_a_time_of_the_source() -> None:
    assert split_section(SECTIONS, 21.5) == [
        (10.0, 12.0),
        (20.0, 21.5),
        (21.5, 23.0),
        (30.0, 31.0),
    ]
    for at in (20.0, 15.0):
        with pytest.raises(ClipEditError, match="no section plays"):
            split_section(SECTIONS, at)


def test_delete_a_section_but_not_the_last_one() -> None:
    assert delete_section(SECTIONS, 1) == [(10.0, 12.0), (30.0, 31.0)]
    with pytest.raises(ClipEditError, match="only section"):
        delete_section(SECTIONS[:1], 0)
    with pytest.raises(SectionNotFound):
        delete_section(SECTIONS, -1)


def test_rearrange_needs_each_index_once() -> None:
    assert reorder_sections(SECTIONS, [2, 0, 1]) == [
        (30.0, 31.0),
        (10.0, 12.0),
        (20.0, 23.0),
    ]
    for order in ([0, 1], [0, 1, 1], [0, 1, 3]):
        with pytest.raises(ClipEditError, match="is not each of 0..2 once"):
            reorder_sections(SECTIONS, order)


def test_section_problems() -> None:
    assert section_problems(SECTIONS, 60.0, FPS) == []
    assert section_problems([(1.0, 1.01), (2.0, 70.0)], 60.0, FPS) == [
        "section 0 is shorter than a frame",
        "section 1 ends after the end of the video (60)",
    ]
    assert section_problems([(5.0, 8.0), (1.0, 6.0)], 60.0, FPS) == [
        "sections overlap at [5, 6]"
    ]


def test_cuts_keep_their_parts_inside_the_sections() -> None:
    cuts = [(11.0, 21.0), (25.0, 26.0), (30.2, 30.4)]

    assert fit_cuts(cuts, SECTIONS) == [(11.0, 12.0), (20.0, 21.0), (30.2, 30.4)]


def test_the_gaps_between_sections_are_cut() -> None:
    rearranged = [(30.0, 31.0), (10.0, 12.0), (20.0, 23.0)]

    assert section_gaps(rearranged) == [(12.0, 20.0), (23.0, 30.0)]
    assert with_gaps([(21.0, 21.5)], rearranged) == [
        (12.0, 20.0),
        (21.0, 21.5),
        (23.0, 30.0),
    ]


def test_parts_play_in_the_sections_order() -> None:
    rearranged = [(30.0, 31.0), (10.0, 12.0), (20.0, 23.0)]

    played = played_spans(10.0, 31.0, rearranged, [(21.0, 21.5)], FPS)

    assert played == [(20.0, 21.0), (0.0, 2.0), (10.0, 11.0), (11.5, 13.0)]


def test_one_section_plays_as_v1_kept_it() -> None:
    cuts = [(10.31, 10.62), (11.0, 11.2)]

    assert played_spans(10.0, 12.5, [(10.0, 12.5)], cuts, FPS) == kept_spans(
        10.0, 12.5, cuts, FPS
    )


def test_touching_sections_play_apart() -> None:
    split = [(11.0, 12.0), (10.0, 11.0)]

    assert played_spans(10.0, 12.0, split, [], FPS) == [(1.0, 2.0), (0.0, 1.0)]


def test_words_move_with_their_sections() -> None:
    transcript = said(("first", 10.2, 10.5), ("second", 12.2, 12.6))
    clip = make_clip("karaoke_bold", segments=[(12.0, 13.0), (10.0, 11.0)])

    words = spoken_words(transcript, clip, FPS)

    assert [(w.text, w.start, w.end) for w in words] == [
        ("second", 200, 600),
        ("first", 1200, 1500),
    ]


def test_a_word_ends_with_its_part() -> None:
    words = [CaptionWord("a", 900, 1300), CaptionWord("b", 1300, 1400)]

    moved = reorder_words(words, [(1.0, 2.0), (0.0, 1.0)])

    assert [(w.text, w.start, w.end) for w in moved] == [
        ("b", 300, 400),
        ("a", 1900, 2000),
    ]


def test_words_of_sections_in_source_order_stay() -> None:
    words = [CaptionWord("a", 100, 300)]

    assert reorder_words(words, [(0.0, 1.0), (2.0, 3.0)]) == words


def test_clip_length_leaves_out_the_gaps() -> None:
    clip = make_clip(
        "karaoke_bold",
        segments=[(30.0, 31.0), (10.0, 12.0)],
        cut_ranges=[(10.5, 11.0)],
    )

    assert clip_length(clip, FPS) == pytest.approx(2.5)


def test_the_preview_key_changes_with_the_sections_order() -> None:
    plan = plan_at(0, 0, 0)
    spans: list[SourceSpan] = [(10.0, 11.0), (12.0, 13.0)]
    ordered = make_clip("karaoke_bold", segments=spans, tracks=timeline_of(spans))
    swapped = make_clip(
        "karaoke_bold", segments=spans[::-1], tracks=timeline_of(spans[::-1])
    )

    assert preview_key(ordered, plan) != preview_key(swapped, plan)


def test_respan_moves_the_earliest_and_latest_sections() -> None:
    rearranged = [(30.0, 31.0), (10.0, 12.0)]

    assert respan(rearranged, 9.0, 32.0) == [(30.0, 32.0), (9.0, 12.0)]


def test_cuts_and_gaps_may_not_leave_nothing() -> None:
    problems = edit_problems(
        10.0, 21.0, [(10.0, 11.0)], "karaoke_bold", 60.0, [(10.0, 11.0), (20.0, 21.0)]
    )
    everything = edit_problems(
        10.0, 21.0, [(10.0, 11.0), (20.0, 21.0)], "karaoke_bold", 60.0,
        [(10.0, 11.0), (20.0, 21.0)],
    )  # fmt: skip

    assert problems == []
    assert everything == ["the cut ranges leave nothing of the clip"]
