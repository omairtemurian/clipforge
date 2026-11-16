"""The Pro Edit EDL schema: good and bad params for every kind, the clip end,
the overlap rules of the tracks and the stackable limits (SPEC-v3 3.1)."""

from typing import Any, get_args

import pytest
from clipforge.models import EdlItem, EdlKind, ProEditPlan
from clipforge.proedit.edl import (
    STACKABLE,
    TRACK_OF_KIND,
    EdlValidationError,
    parse_item,
    plan_problems,
    validate_plan,
)

CLIP_DURATION = 30.0

# kind -> (params that are valid, params that are not, text of the problem)
CASES: dict[str, tuple[dict[str, Any], dict[str, Any], str]] = {
    "zoom_punch": ({"scale": 1.25}, {"scale": 1.6}, "params.scale"),
    "zoom_push": (
        {"scale_from": 1.0, "scale_to": 1.12},
        {"scale_from": 1.2, "scale_to": 1.1},
        "scale_to must be larger",
    ),
    "zoom_out_reveal": (
        {"scale_from": 1.2},
        {"scale_from": 1.2, "scale_to": 1.3},
        "scale_to must be smaller",
    ),
    "pan": (
        {"from_x": 0.2, "from_y": 0.5, "to_x": 0.8, "to_y": 0.5},
        {"from_x": 0.2, "from_y": 0.5, "to_x": 0.2, "to_y": 0.5},
        "end somewhere else",
    ),
    "shake": ({"strength": 0.6}, {"strength": 2}, "params.strength"),
    "flash": ({"color": "white"}, {"color": "red"}, "params.color"),
    "glitch": ({"seed": 7}, {"seed": "x"}, "params.seed"),
    "rgb_split": ({"offset_px": 10}, {"offset_px": 0}, "params.offset_px"),
    "freeze_frame": ({}, {"hold": 1}, "params.hold"),
    "speed_ramp": (
        {"speed_from": 1.0, "speed_to": 0.3},
        {"speed_from": 1.0, "speed_to": 1.0},
        "speed_to must differ",
    ),
    "slowmo": ({"speed": 0.4}, {"speed": 1.5}, "params.speed"),
    "transition": ({"type": "whip"}, {"type": "wipe"}, "params.type"),
    "grade_change": (
        {"look": "lut", "lut": "teal_orange"},
        {"look": "bw", "lut": "teal_orange"},
        "lut is only for the lut look",
    ),
    "vignette": ({"strength": 0.5}, {"strength": 0}, "params.strength"),
    "grain": ({"strength": 0.3, "seed": 3}, {"strength": 1.5}, "params.strength"),
    "overlay": (
        {"asset": "skull", "anchor": "face"},
        {"asset": "skull", "anchor": "head"},
        "params.anchor",
    ),
    "text_pop": ({"text": "WAIT"}, {"text": ""}, "params.text"),
    "emoji_pop": ({"emoji": "💀"}, {"emoji": ""}, "params.emoji"),
    "caption_style": ({"style": "neon"}, {"style": "comic"}, "params.style"),
    "sfx": ({"asset": "whoosh_1", "gain_db": -8}, {"gain_db": -8}, "params.asset"),
    "music_bed": (
        {"asset": "bed_1", "gain_db": -20},
        {"asset": "bed_1", "gain_db": 6},
        "params.gain_db",
    ),
    "silence_before_drop": ({}, {"asset": "x"}, "params.asset"),
    "audio_fx": (
        {"effect": "reverb_tail"},
        {"effect": "autotune"},
        "params.effect",
    ),
}
# The silence before a drop is the only kind with a length rule of its own.
LENGTH_OF = {"silence_before_drop": 0.2}


def item(
    kind: str,
    item_id: int = 1,
    t_start: float = 1.0,
    t_end: float = 2.0,
    params: dict[str, Any] | None = None,
) -> EdlItem:
    """An item of the kind with its valid params (or the given ones)."""
    if kind in LENGTH_OF and t_end - t_start != LENGTH_OF[kind]:
        t_end = t_start + LENGTH_OF[kind]
    return EdlItem.model_validate(
        {
            "id": item_id,
            "t_start": t_start,
            "t_end": t_end,
            "kind": kind,
            "params": CASES[kind][0] if params is None else params,
            "reason": "the speaker lands the punchline",
        }
    )


def plan(*items: EdlItem) -> ProEditPlan:
    """A plan of the items."""
    return ProEditPlan(
        id=1,
        clip_id=1,
        preset="clean_pro",
        intensity="standard",
        version=1,
        items=list(items),
        created_by="rule_director",
    )


def test_cases_cover_every_kind() -> None:
    assert set(CASES) == set(get_args(EdlKind)) == set(TRACK_OF_KIND)
    assert len(CASES) == 23


@pytest.mark.parametrize("kind", sorted(CASES))
def test_good_params_of_every_kind_validate(kind: str) -> None:
    typed = validate_plan(plan(item(kind)), CLIP_DURATION)

    assert [i.kind for i in typed] == [kind]


@pytest.mark.parametrize("kind", sorted(CASES))
def test_bad_params_of_every_kind_name_the_item_and_the_param(kind: str) -> None:
    _, bad, expected = CASES[kind]

    with pytest.raises(EdlValidationError) as error:
        validate_plan(plan(item(kind, item_id=4, params=bad)), CLIP_DURATION)

    assert len(error.value.problems) == 1
    assert f"item 4 ({kind})" in error.value.problems[0]
    assert expected in error.value.problems[0]


def test_parse_item_fills_the_defaults_of_the_kind() -> None:
    typed = parse_item(item("zoom_punch", params={}))

    assert typed.kind == "zoom_punch"
    assert typed.params.scale == 1.2 and typed.params.center == "face"


def test_a_zoom_punch_eases_over_zero_or_two_to_four_frames() -> None:
    for frames in (0, 2, 3, 4):
        parse_item(item("zoom_punch", params={"ease_frames": frames}))
    for frames in (1, 5):
        with pytest.raises(EdlValidationError):
            parse_item(item("zoom_punch", params={"ease_frames": frames}))


def test_the_lut_look_needs_a_lut_name() -> None:
    with pytest.raises(EdlValidationError, match="needs a lut name"):
        parse_item(item("grade_change", params={"look": "lut"}))


def test_unknown_params_are_rejected() -> None:
    with pytest.raises(EdlValidationError, match="params.shiny"):
        parse_item(item("flash", params={"color": "white", "shiny": True}))


def test_the_reason_is_required() -> None:
    with pytest.raises(ValueError):
        EdlItem(id=1, t_start=0, t_end=1, kind="flash", reason="")
    with pytest.raises(ValueError):
        EdlItem(id=1, t_start=0, t_end=1, kind="flash", reason="   ")


def test_the_source_is_auto_or_manual() -> None:
    manual = item("flash").model_copy(update={"source": "manual"})
    assert validate_plan(plan(manual), CLIP_DURATION)[0].source == "manual"
    with pytest.raises(ValueError):
        EdlItem.model_validate({**manual.model_dump(), "source": "llm"})


def test_an_item_past_the_clip_end_is_rejected_with_its_id() -> None:
    late = item("flash", item_id=9, t_start=29.5, t_end=30.5)

    problems = plan_problems(plan(late), CLIP_DURATION)

    assert problems == ["item 9 (flash) ends at 30.5 s, past the clip end at 30 s"]


def test_an_item_that_ends_exactly_at_the_clip_end_is_valid() -> None:
    last = item("flash", t_start=29.0, t_end=30.0)

    assert plan_problems(plan(last), CLIP_DURATION) == []


def test_overlapping_items_of_one_track_are_rejected_with_both_ids() -> None:
    a = item("glitch", item_id=2, t_start=1.0, t_end=2.0)
    b = item("flash", item_id=5, t_start=1.5, t_end=2.5)

    problems = plan_problems(plan(a, b), CLIP_DURATION)

    assert problems == [
        "items 2 (glitch, 1-2 s) and 5 (flash, 1.5-2.5 s) overlap on the fx track"
    ]


def test_items_that_touch_do_not_overlap() -> None:
    a = item("shake", item_id=1, t_start=1.0, t_end=2.0)
    b = item("flash", item_id=2, t_start=2.0, t_end=3.0)

    assert plan_problems(plan(a, b), CLIP_DURATION) == []


def test_items_of_different_tracks_may_overlap() -> None:
    items = [
        item("zoom_punch", 1, 1.0, 2.0),
        item("shake", 2, 1.0, 2.0),
        item("vignette", 3, 1.0, 2.0),
        item("caption_style", 4, 1.0, 2.0),
        item("audio_fx", 5, 1.0, 2.0),
        item("sfx", 6, 1.0, 2.0),
        item("music_bed", 7, 0.0, 0.5),
        item("overlay", 8, 1.0, 2.0),
    ]

    assert plan_problems(plan(*items), CLIP_DURATION) == []


def test_every_track_rejects_an_overlap_of_its_exclusive_kinds() -> None:
    pairs: list[tuple[EdlKind, EdlKind]] = [
        ("zoom_punch", "pan"),
        ("grade_change", "grade_change"),
        ("glitch", "freeze_frame"),
        ("overlay", "overlay"),
        ("caption_style", "caption_style"),
        ("music_bed", "silence_before_drop"),
        ("audio_fx", "audio_fx"),
    ]
    for first, second in pairs:
        a = item(first, 1, 1.0, 2.0)
        b = item(second, 2, 1.1, 1.3)

        problems = plan_problems(plan(a, b), CLIP_DURATION)

        assert len(problems) == 1, (first, second, problems)
        assert "items 1" in problems[0] and "and 2" in problems[0]
        assert TRACK_OF_KIND[first] in problems[0]


def test_layer_kinds_lie_over_their_track_but_not_over_themselves() -> None:
    under: dict[EdlKind, EdlKind] = {
        "vignette": "grade_change",
        "grain": "grade_change",
        "shake": "freeze_frame",
    }
    for layer, base in under.items():
        over = plan(item(base, 1, 1.0, 2.0), item(layer, 2, 1.1, 1.3))
        twice = plan(item(layer, 1, 1.0, 2.0), item(layer, 2, 1.1, 1.3))

        assert plan_problems(over, CLIP_DURATION) == [], layer
        assert len(plan_problems(twice, CLIP_DURATION)) == 1, layer


def test_an_unsorted_plan_is_checked_the_same() -> None:
    a = item("glitch", 1, 5.0, 6.0)
    b = item("flash", 2, 1.0, 2.0)
    c = item("rgb_split", 3, 5.5, 6.5)

    assert len(plan_problems(plan(a, b, c), CLIP_DURATION)) == 1


def test_stackable_kinds_overlap_up_to_their_limit() -> None:
    pops = [
        item("text_pop", 1, 1.0, 2.0),
        item("emoji_pop", 2, 1.0, 2.0),
        item("text_pop", 3, 1.0, 2.0),
    ]
    sfx = [item("sfx", 4, 1.0, 1.5), item("sfx", 5, 1.2, 1.7)]

    assert plan_problems(plan(*pops, *sfx), CLIP_DURATION) == []
    assert STACKABLE == {"text_pop", "emoji_pop", "sfx"}


def test_a_fourth_concurrent_pop_is_rejected_with_the_ids() -> None:
    pops = [item("emoji_pop", n, 1.0 + n * 0.1, 3.0) for n in range(1, 5)]

    problems = plan_problems(plan(*pops), CLIP_DURATION)

    assert len(problems) == 1
    assert "items 1, 2, 3, 4" in problems[0]
    assert "at most 3" in problems[0]


def test_a_third_concurrent_sfx_is_rejected() -> None:
    sfx = [item("sfx", n, 1.0, 2.0) for n in range(1, 4)]

    problems = plan_problems(plan(*sfx), CLIP_DURATION)

    assert len(problems) == 1 and "at most 2" in problems[0]


def test_stackable_kinds_do_not_conflict_with_the_overlay_kind() -> None:
    overlay = item("overlay", 1, 1.0, 3.0)
    pops = [item("text_pop", n, 1.0, 3.0) for n in range(2, 5)]

    assert plan_problems(plan(overlay, *pops), CLIP_DURATION) == []


def test_the_silence_before_a_drop_lasts_100_to_300_ms() -> None:
    def silence(length: float) -> EdlItem:
        return item("silence_before_drop").model_copy(
            update={"t_start": 5.0, "t_end": 5.0 + length}
        )

    for length in (0.1, 0.2, 0.3):
        assert plan_problems(plan(silence(length)), CLIP_DURATION) == []
    for length in (0.05, 0.5):
        problems = plan_problems(plan(silence(length)), CLIP_DURATION)
        assert len(problems) == 1 and "0.1 to 0.3 s" in problems[0]


def test_validate_plan_returns_the_items_in_time_order() -> None:
    late = item("flash", 1, 8.0, 9.0)
    early = item("zoom_punch", 2, 1.0, 1.2)

    typed = validate_plan(plan(late, early), CLIP_DURATION)

    assert [i.id for i in typed] == [2, 1]


def test_all_problems_are_reported_together() -> None:
    bad = item("zoom_punch", 1, params={"scale": 3})
    late = item("flash", 2, 29.5, 31.0)
    a = item("rgb_split", 3, 5.0, 6.0)
    b = item("glitch", 4, 5.5, 6.5)

    with pytest.raises(EdlValidationError) as error:
        validate_plan(plan(bad, late, a, b), CLIP_DURATION)

    assert len(error.value.problems) == 3
    assert "item 1" in str(error.value) and "item 2" in str(error.value)


def test_an_empty_plan_is_valid() -> None:
    assert validate_plan(plan(), CLIP_DURATION) == []
