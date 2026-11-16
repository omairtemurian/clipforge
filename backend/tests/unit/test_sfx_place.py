"""Unit tests of the Pro Edit whoosh placement (SPEC-v3 3.3, TASK-214):
every zoom, transition, pop-in and hard cut gets a whoosh as long as its
motion, varied in pitch, within the intensity's SFX budget and clear of
punchline words."""

import pytest
from clipforge.models import EdlItem
from clipforge.proedit.audio.sfx_place import (
    INSTANT_WHOOSH_S,
    PITCH_VARIANTS,
    VisualEvent,
    place_whooshes,
    visual_events,
    whoosh_asset,
    whoosh_frames,
)
from clipforge.proedit.budgets import Density, PresetBudget
from clipforge.proedit.edl import parse_item
from clipforge.proedit.snap import PlanTiming
from edl_fakes import item, plan

FPS = 30
TIMING = PlanTiming(FPS, 10.0)
FRAME = {"center": "frame"}


def sfx_of(items: list[EdlItem]) -> list[EdlItem]:
    return [i for i in items if i.kind == "sfx"]


def spans(items: list[EdlItem]) -> list[tuple[float, float]]:
    return [(i.t_start, i.t_end) for i in sfx_of(items)]


def test_every_visual_event_has_its_motion_in_priority_order() -> None:
    items = [
        item(1, "zoom_push", 0.4, 1.2, params=FRAME),
        item(2, "zoom_punch", 3.0, 3.5, params=FRAME),
        item(3, "zoom_punch", 2.0, 2.5, params={**FRAME, "ease_frames": 4}),
        item(4, "transition", 5.0, 5.5, params={"type": "whip"}),
        item(5, "transition", 6.0, 6.5, params={"whoosh": False}),
        item(6, "text_pop", 7.0, 8.0, params={"text": "WOW"}),
        item(7, "text_pop", 8.0, 9.0, params={"text": "WOW", "animation": "bounce"}),
        item(8, "emoji_pop", 9.0, 9.1, params={"emoji": "x", "animation": "slide"}),
        item(9, "text_pop", 4.0, 5.0, params={"text": "A", "animation": "none"}),
        item(10, "grade_change", 0.0, 2.0),
    ]
    events = visual_events([parse_item(i) for i in items], cuts=(1.5,), fps=FPS)
    assert [(e.kind, e.start, e.end, e.what) for e in events] == [
        ("transition", 5.0, 5.5, "the transition item 4"),
        ("zoom", 0.4, 1.2, "the zoom_push item 1"),
        ("zoom", 2.0, pytest.approx(2.0 + 4 / 30), "the zoom_punch item 3"),
        ("zoom", 3.0, 3.0, "the zoom_punch item 2"),
        ("cut", 1.5, 1.5, "the cut at 1.5 s"),
        ("pop", 4.0, 4.0, "the text_pop item 9"),
        ("pop", 7.0, pytest.approx(7.2), "the text_pop item 6"),
        ("pop", 8.0, pytest.approx(8.4), "the text_pop item 7"),
        ("pop", 9.0, pytest.approx(9.1), "the emoji_pop item 8"),
    ]


@pytest.mark.parametrize(
    ("start", "end", "frames"),
    [
        (0.4, 1.2, (12, 36)),  # a motion: its frames
        (2.0, 2.1, (60, 63)),  # 3 frames: long enough
        (3.0, 3.0, (86, 95)),  # instant: 9 frames (0.3 s) centred on it
        (3.0, 3.0 + 2 / 30, (87, 96)),  # 2 frames: centred on its middle
        (0.0, 0.0, (0, 5)),  # kept inside the clip
        (10.0, 10.0, (296, 300)),
    ],
)
def test_a_whoosh_lasts_the_motion_or_centres_on_an_instant(
    start: float, end: float, frames: tuple[int, int]
) -> None:
    event = VisualEvent("zoom", start, end, "x")
    assert whoosh_frames(event, TIMING) == frames
    assert round(INSTANT_WHOOSH_S * FPS) == 9


@pytest.mark.parametrize(
    ("seconds", "asset"),
    [(0.2, "whoosh_swift"), (0.5, "whoosh_swift"), (0.67, "whoosh_swift")]
    + [(0.68, "whoosh_soft"), (0.9, "whoosh_soft"), (2.0, "whoosh_soft")],
)
def test_the_whoosh_nearest_the_length_in_ratio_is_chosen(
    seconds: float, asset: str
) -> None:
    assert whoosh_asset(seconds) == asset


def test_a_zoom_gets_a_stretched_whoosh_as_long_as_its_motion() -> None:
    zoom = item(4, "zoom_push", 0.4, 1.2, params=FRAME)
    placed = place_whooshes(plan([zoom], "extreme"), TIMING)
    assert placed.notes == []
    assert placed.plan.items == [
        zoom,
        EdlItem(
            id=5,
            kind="sfx",
            t_start=0.4,
            t_end=1.2,
            params={
                "asset": "whoosh_soft",
                "gain_db": -8.0,
                "pitch_semitones": 0.0,
                "fit": "stretch",
            },
            reason="whoosh on the zoom_push item 4 (0.80 s)",
            source="auto",
        ),
    ]
    parse_item(placed.plan.items[1])


def test_successive_whooshes_cycle_their_pitch_with_new_ids() -> None:
    cuts = (1.5, 3.0, 4.5, 6.0, 7.5, 9.0)
    placed = place_whooshes(plan([], "extreme"), TIMING, cuts=cuts)
    whooshes = sfx_of(placed.plan.items)
    assert [w.id for w in whooshes] == [1, 2, 3, 4, 5, 6]
    assert [w.params["pitch_semitones"] for w in whooshes] == [
        *PITCH_VARIANTS,
        PITCH_VARIANTS[0],
    ]
    assert spans(placed.plan.items) == [
        ((round(t * FPS) - 4) / FPS, (round(t * FPS) + 5) / FPS) for t in cuts
    ]


def test_an_event_already_sounded_or_unwanted_gets_no_whoosh() -> None:
    items = [
        item(1, "zoom_push", 0.4, 1.2, params=FRAME),
        item(2, "sfx", 1.0, 1.5, source="manual"),
        item(3, "transition", 3.0, 3.5, params={"whoosh": False}),
        item(4, "zoom_punch", 6.0, 6.5, params=FRAME),
    ]
    sounded = place_whooshes(plan(items[:3], "extreme"), TIMING)
    assert sounded.plan.items == items[:3]
    only_zooms = place_whooshes(
        plan(items[2:], "extreme"), TIMING, cuts=(8.0,), events=frozenset({"zoom"})
    )
    assert [w.reason for w in sfx_of(only_zooms.plan.items)] == [
        "whoosh on the zoom_punch item 4 (0.30 s)"
    ]


def test_the_budget_drops_whooshes_of_lower_priority_with_a_note() -> None:
    # Pro allows one SFX start per 2 s: the transition at 2.0 s wins over
    # the earlier cut and pop.
    items = [
        item(1, "transition", 2.0, 2.5),
        item(2, "text_pop", 2.5, 3.5, params={"text": "WOW"}),
    ]
    placed = place_whooshes(plan(items, "pro"), TIMING, cuts=(1.0,))
    assert spans(placed.plan.items) == [(2.0, 2.5)]
    assert [(n.item_id, n.kind, n.action) for n in placed.notes] == [
        (4, "sfx", "dropped"),
        (5, "sfx", "dropped"),
    ]
    assert placed.notes[0].reason == (
        "the whoosh would break a rule: 2 sfx items start within 2 s; "
        "the pro budget allows 1"
    )


@pytest.mark.parametrize(
    ("intensity", "preset", "kept"),
    [
        ("extreme", None, [1.0, 2.0, 4.0, 6.0, 8.0]),
        ("pro", None, [1.0, 4.0, 6.0, 8.0]),
        ("standard", None, [1.0, 6.0]),
        ("clean", None, [1.0, 8.0]),
        ("standard", PresetBudget(kinds={"sfx": Density(count=1, window_s=8)}), [1.0]),
    ],
)
def test_the_intensity_and_preset_set_the_whoosh_density(
    intensity: str, preset: PresetBudget | None, kept: list[float]
) -> None:
    cuts = (1.0, 2.0, 4.0, 6.0, 8.0)
    placed = place_whooshes(
        plan([], intensity),  # type: ignore[arg-type]
        TIMING,
        cuts=[c + 4 / FPS for c in cuts],
        preset_budget=preset,
    )
    assert [round(s * FPS) / FPS for s, _ in spans(placed.plan.items)] == kept
    assert len(placed.notes) == len(cuts) - len(kept)


def test_a_whoosh_over_a_punchline_moves_before_it_or_is_dropped() -> None:
    timing = PlanTiming(FPS, 10.0, punchlines=((3.0, 3.4), (0.1, 0.5)))
    items = [
        item(1, "zoom_punch", 3.0, 3.5, params=FRAME),
        item(2, "zoom_punch", 0.2, 0.7, params=FRAME),
    ]
    placed = place_whooshes(plan(items, "extreme"), timing)
    assert spans(placed.plan.items) == [(80 / 30, 89 / 30)]
    assert {n.item_id: n.action for n in placed.notes} == {3: "dropped", 4: "moved"}


@pytest.mark.parametrize("punch_at", [x / 10 for x in range(5, 95, 3)])
def test_no_whoosh_ever_sounds_over_a_punchline(punch_at: float) -> None:
    punchlines = ((punch_at, punch_at + 0.4), (punch_at + 1.3, punch_at + 1.5))
    timing = PlanTiming(FPS, 10.0, punchlines=punchlines)
    items = [
        item(1, "zoom_push", max(punch_at - 0.5, 0), punch_at + 0.2, params=FRAME),
        item(2, "text_pop", punch_at + 1.0, punch_at + 2.0, params={"text": "W"}),
    ]
    cuts = (punch_at + 0.1, punch_at + 1.4)
    placed = place_whooshes(plan(items, "extreme"), timing, cuts=cuts)
    for start, end in spans(placed.plan.items):
        for word_start, word_end in punchlines:
            assert end <= word_start + 1e-9 or start >= word_end - 1e-9


def test_the_sfx_stack_limit_drops_a_third_sound() -> None:
    items = [
        item(1, "sfx", 0.5, 2.7, source="manual"),
        item(2, "sfx", 1.6, 2.7, source="manual"),
        item(3, "zoom_punch", 2.7, 3.0, params=FRAME),
    ]
    placed = place_whooshes(plan(items, "extreme"), TIMING)
    assert placed.plan.items == items
    assert [n.reason for n in placed.notes] == [
        "the whoosh would break a rule: items 1, 2, 4 are 3 sfx items at "
        "2.56667 s; at most 2 may be on screen or sound together"
    ]
