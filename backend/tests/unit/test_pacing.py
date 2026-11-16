"""J and L cuts (SPEC-v3 3.3 pacing, TASK-233): the sound of each cut of a
Pro Edit render switches 2-8 frames before or after its picture, never
adding or dropping a word, and the graph that plays them."""

from dataclasses import replace
from pathlib import Path

import pytest
from clipforge.pipeline.render_graph import cut_graph
from clipforge.proedit.pacing import (
    JL_FRAMES,
    audio_spans,
    jl_shifts,
    jl_spans,
)
from proedit_render import base_of

FPS = 30
SPANS = [(0.0, 1.0), (2.0, 4.0)]


def test_a_cut_with_no_words_near_it_is_a_j_cut() -> None:
    assert jl_shifts(SPANS, [], 4.0, FPS, 6) == [pytest.approx(-6 / FPS)]
    assert jl_spans(SPANS, [], 4.0, FPS, 6) == [
        pytest.approx((0.0, 0.8)),
        pytest.approx((1.8, 4.0)),
    ]


def test_a_word_before_the_next_part_makes_it_an_l_cut() -> None:
    words = [(1.75, 1.95)]
    assert jl_shifts(SPANS, words, 4.0, FPS, 6) == [pytest.approx(6 / FPS)]


def test_the_shift_shrinks_until_no_word_is_added_or_dropped() -> None:
    # A word ends 4 frames before the cut: the J cut fits 4 frames. With a
    # word right before the next part (no J cut) and one 3 frames into it,
    # the L cut fits 3.
    words = [(0.5, 1.0 - 4 / FPS), (2.0 + 3 / FPS, 2.5), (1.9, 2.0)]
    assert jl_shifts(SPANS, words[:2], 4.0, FPS, 8) == [pytest.approx(-4 / FPS)]
    assert jl_shifts(SPANS, words[1:], 4.0, FPS, 8) == [pytest.approx(3 / FPS)]


def test_a_cut_between_words_stays_straight() -> None:
    words = [(0.9, 1.0), (1.9, 2.1)]
    assert jl_shifts(SPANS, words, 4.0, FPS, 8) == [0.0]
    assert jl_spans(SPANS, words, 4.0, FPS, 8) is None


def test_the_added_sound_stays_in_the_clip() -> None:
    # The next part starts at the clip start (a J cut would play sound
    # before it) and the last ends at the clip end (an L cut, after it).
    assert jl_shifts([(1.0, 1.9), (0.0, 0.1)], [], 1.9, FPS, 6) == [0.0]
    assert jl_shifts([(0.0, 1.0), (1.05, 1.95)], [], 1.95, FPS, 6) == [
        pytest.approx(-6 / FPS)
    ]


def test_contiguous_parts_and_light_settings_have_no_j_or_l_cut() -> None:
    assert jl_shifts([(0.0, 1.0), (1.0, 2.0)], [], 2.0, FPS, 6) == [0.0]
    assert jl_spans(SPANS, [], 4.0, FPS, 0) is None
    assert jl_spans([(0.0, 4.0)], [], 4.0, FPS, 6) is None
    assert JL_FRAMES == {"clean": 2, "standard": 4, "pro": 6, "extreme": 8}


def test_the_sound_lasts_as_long_as_the_picture() -> None:
    spans = [(0.0, 1.0), (2.0, 3.0), (3.5, 4.0)]
    shifts = jl_shifts(spans, [], 4.0, FPS, 8)
    moved = audio_spans(spans, shifts)
    assert sum(e - s for s, e in moved) == pytest.approx(sum(e - s for s, e in spans))
    assert all(abs(shift) >= 2 / FPS for shift in shifts)


def test_the_base_moves_the_sound_of_its_cuts() -> None:
    base = replace(
        base_of(Path("source.mp4"), [(2.0, 3.0)]), source_words=((1.75, 1.95),)
    )
    assert base.audio_cuts(FPS) is None
    pro = replace(base, jl_frames=6)
    assert pro.audio_cuts(FPS) == [
        pytest.approx((0.0, 1.2)),
        pytest.approx((2.2, 4.0)),
    ]


def test_cut_graph_joins_the_moved_sound_on_its_own() -> None:
    straight = cut_graph(SPANS, ("[0:a]", "[a]"), ("[v0]", "[v]"))
    moved = cut_graph(
        SPANS, ("[0:a]", "[a]"), ("[v0]", "[v]"), (), [(0, 0.8), (1.8, 4)]
    )
    assert "concat=n=2:v=1:a=1" in straight
    assert "[kept_v0][kept_v1]concat=n=2:v=1:a=0[v]" in moved
    assert "[kept_a0][kept_a1]concat=n=2:v=0:a=1[a]" in moved
    assert "atrim=start=1.800000:end=4.000000" in moved
    assert "trim=start=2.000000:end=4.000000" in moved
