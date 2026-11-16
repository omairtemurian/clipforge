"""Pro Edit post-processing (SPEC-v3 3.1): frame, word and beat snapping with
exact numbers and SFX kept off punchline words. The budgets are in
test_edl_budgets.py."""

import pytest
from clipforge.proedit.snap import (
    PlanTiming,
    nearest,
    protect_punchlines,
    snap_items,
)
from edl_fakes import item, times

T30 = PlanTiming(fps=30, duration=30.0)


# --- frame snapping ---------------------------------------------------------


def test_times_snap_to_the_frame_grid() -> None:
    snapped, notes = snap_items([item(1, "zoom_push", 1.01, 2.49)], T30)
    assert times(snapped) == {1: (30 / 30, 75 / 30)}
    assert notes == []


def test_frame_grid_at_25_and_29_97_fps() -> None:
    snapped, _ = snap_items(
        [item(1, "vignette", 0.43, 0.51)], PlanTiming(fps=25, duration=10)
    )
    assert times(snapped) == {1: (11 / 25, 13 / 25)}
    ntsc = 30000 / 1001
    snapped, _ = snap_items(
        [item(1, "vignette", 1.0, 2.0)], PlanTiming(fps=ntsc, duration=10)
    )
    assert times(snapped) == {1: (30 / ntsc, 60 / ntsc)}
    assert snapped[0].t_start == pytest.approx(1.001)


def test_an_item_shorter_than_a_frame_lasts_one_frame() -> None:
    snapped, _ = snap_items([item(1, "flash", 1.0, 1.01)], T30)
    assert times(snapped) == {1: (30 / 30, 31 / 30)}


def test_the_end_stays_on_the_last_whole_frame_of_the_clip() -> None:
    timing = PlanTiming(fps=30, duration=10.01)
    assert timing.last_frame == 300
    snapped, _ = snap_items([item(1, "grain", 9.0, 10.01)], timing)
    assert times(snapped) == {1: (270 / 30, 300 / 30)}


def test_timing_rejects_bad_fps_and_sorts_its_marks() -> None:
    with pytest.raises(ValueError, match="fps"):
        PlanTiming(fps=0, duration=5)
    with pytest.raises(ValueError, match="one frame"):
        PlanTiming(fps=30, duration=0.01)
    timing = PlanTiming(fps=30, duration=5, word_starts=(2.0, 1.0), beats=(3.0, 0.5))
    assert timing.word_starts == (1.0, 2.0)
    assert timing.beats == (0.5, 3.0)


# --- word snapping ----------------------------------------------------------


def test_word_items_start_on_the_nearest_word_within_a_quarter_second() -> None:
    timing = PlanTiming(fps=30, duration=30, word_starts=(1.70, 2.30, 2.95))
    snapped, _ = snap_items([item(1, "text_pop", 2.10, 2.60)], timing)
    # 0.2 s to the word at 2.30; the 0.5 s length (15 frames) is kept.
    assert times(snapped) == {1: (69 / 30, 84 / 30)}


def test_a_word_farther_than_a_quarter_second_is_not_used() -> None:
    timing = PlanTiming(fps=30, duration=30, word_starts=(2.26,))
    snapped, _ = snap_items([item(1, "text_pop", 2.0, 2.5)], timing)
    assert times(snapped) == {1: (60 / 30, 75 / 30)}


def test_nearest_takes_the_earlier_time_on_a_tie_and_respects_the_window() -> None:
    assert nearest((1.9, 2.1), 2.0, 0.25) == 1.9
    assert nearest((1.0, 3.0), 2.0, 0.25) is None
    assert nearest((), 2.0, 0.25) is None
    assert nearest((2.25,), 2.0, 0.25) == 2.25


# --- beat snapping ----------------------------------------------------------


def test_beat_items_start_on_the_nearest_beat_within_0_12_s() -> None:
    timing = PlanTiming(fps=30, duration=30, beats=(2.5, 3.0, 3.5))
    snapped, _ = snap_items([item(1, "flash", 3.05, 3.15)], timing)
    assert times(snapped) == {1: (90 / 30, 93 / 30)}


def test_beat_items_without_a_near_beat_use_a_word_then_the_frame() -> None:
    timing = PlanTiming(fps=30, duration=30, beats=(3.0, 3.5), word_starts=(3.1,))
    snapped, _ = snap_items([item(1, "flash", 3.2, 3.3)], timing)
    assert times(snapped) == {1: (93 / 30, 96 / 30)}
    no_word = PlanTiming(fps=30, duration=30, beats=(3.0, 3.5))
    snapped, _ = snap_items([item(1, "flash", 3.2, 3.3)], no_word)
    assert times(snapped) == {1: (96 / 30, 99 / 30)}


def test_the_silence_before_a_drop_ends_on_the_beat() -> None:
    timing = PlanTiming(fps=30, duration=30, beats=(10.0,))
    snapped, _ = snap_items([item(1, "silence_before_drop", 9.75, 9.95)], timing)
    assert times(snapped) == {1: (294 / 30, 300 / 30)}


def test_a_preset_can_snap_zoom_punches_to_beats() -> None:
    timing = PlanTiming(fps=24, duration=30, beats=(3.0,), word_starts=(3.2,))
    zoom = [item(1, "zoom_punch", 3.1, 3.5)]
    by_word, _ = snap_items(zoom, timing)
    by_beat, _ = snap_items(zoom, timing, {"zoom_punch": "beat"})
    assert times(by_word) == {1: (77 / 24, 87 / 24)}
    assert times(by_beat) == {1: (72 / 24, 82 / 24)}


def test_snapping_never_makes_items_overlap() -> None:
    timing = PlanTiming(fps=30, duration=30, beats=(3.0,))
    first, second = item(1, "flash", 2.94, 3.04), item(2, "flash", 3.06, 3.2)
    snapped, notes = snap_items([first, second], timing)
    # Either one on the beat would overlap the other: both stay on the grid.
    assert times(snapped) == {1: (88 / 30, 91 / 30), 2: (92 / 30, 96 / 30)}
    assert notes == []
    alone, _ = snap_items([second], timing)
    assert times(alone) == {2: (90 / 30, 94 / 30)}


def test_snapping_does_not_push_a_third_pop_into_a_full_stack() -> None:
    timing = PlanTiming(fps=30, duration=30, word_starts=(1.0,))
    pops = [
        item(1, "text_pop", 1.0, 2.0),
        item(2, "emoji_pop", 1.0, 2.0),
        item(3, "text_pop", 0.5, 1.1),
        item(4, "text_pop", 1.2, 2.0),
    ]
    snapped, notes = snap_items(pops, timing)
    # On the word at 1.0 item 4 would be a fourth pop with 1, 2 and 3.
    assert times(snapped) == {
        1: (30 / 30, 60 / 30),
        2: (30 / 30, 60 / 30),
        3: (15 / 30, 33 / 30),
        4: (36 / 30, 60 / 30),
    }
    assert notes == []
    without_3, _ = snap_items([p for p in pops if p.id != 3], timing)
    assert times(without_3)[4] == (30 / 30, 54 / 30)


# --- punchline protection ---------------------------------------------------


def test_an_sfx_over_a_punchline_ends_one_frame_before_the_word() -> None:
    timing = PlanTiming(fps=30, duration=30, punchlines=((5.0, 5.4),))
    kept, notes = protect_punchlines([item(1, "sfx", 147 / 30, 156 / 30)], timing)
    assert times(kept) == {1: (140 / 30, 149 / 30)}
    assert [(n.item_id, n.action) for n in notes] == [(1, "moved")]
    assert "punchline word at 5 s" in notes[0].reason


def test_an_sfx_that_does_not_fit_before_the_punchline_is_dropped() -> None:
    timing = PlanTiming(fps=30, duration=30, punchlines=((0.2, 0.5),))
    kept, notes = protect_punchlines([item(1, "sfx", 0.1, 0.4)], timing)
    assert kept == []
    assert [(n.item_id, n.action) for n in notes] == [(1, "dropped")]


def test_sfx_touching_the_punchline_and_other_kinds_stay() -> None:
    timing = PlanTiming(fps=30, duration=30, punchlines=((5.0, 5.4),))
    items = [item(1, "sfx", 162 / 30, 171 / 30), item(2, "zoom_punch", 5.0, 5.4)]
    kept, notes = protect_punchlines(items, timing)
    assert times(kept) == times(items)
    assert notes == []


def test_a_moved_sfx_may_not_cover_another_punchline_or_fill_the_stack() -> None:
    two_words = PlanTiming(fps=30, duration=30, punchlines=((4.9, 5.0), (5.1, 5.3)))
    kept, notes = protect_punchlines([item(1, "sfx", 5.15, 5.25)], two_words)
    assert kept == [] and notes[0].action == "dropped"
    one_word = PlanTiming(fps=30, duration=30, punchlines=((5.0, 5.4),))
    stack = [
        item(1, "sfx", 138 / 30, 148 / 30),
        item(2, "sfx", 141 / 30, 148 / 30),
        item(3, "sfx", 147 / 30, 156 / 30),
    ]
    kept, notes = protect_punchlines(stack, one_word)
    assert sorted(times(kept)) == [1, 2]
    assert [(n.item_id, n.action) for n in notes] == [(3, "dropped")]
