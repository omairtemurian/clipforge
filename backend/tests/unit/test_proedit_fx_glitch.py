"""Unit tests of the Pro Edit glitches, RGB splits and transitions (SPEC-v3
3.3 Glitch, TASK-211): seeded glitch windows (stutter, glitch frames), the
RGB split offsets, the window branch, the transition cuts and their xfades,
and the channel-offset heuristic on synthetic frames. The rendered frames
are tested with ffmpeg in tests/pipeline/test_proedit_render_glitch.py."""

import random
from typing import Any, get_args

import cv2
import numpy as np
import pytest
from clipforge.models import EdlKind
from clipforge.pipeline.transitions import Join, join_graph
from clipforge.proedit.edl import TypedEdlItem, parse_item
from clipforge.proedit.edl_params import GlitchParams, TransitionParams
from clipforge.proedit.features.glitches import channel_offset
from clipforge.proedit.render.canvas import Canvas
from clipforge.proedit.render.fx_glitch import (
    STUTTER_SIZE,
    glitch_filters,
    glitch_window,
    split_offsets,
    stutter_frames,
)
from clipforge.proedit.render.fx_transition import (
    XFADE_OF_TYPE,
    TransitionWindow,
    transition_filters,
    transition_windows,
)
from edl_fakes import item

CANVAS = Canvas(30, (540, 960))


def typed(
    kind: EdlKind, t_start: float, t_end: float, id: int = 1, **params: Any
) -> TypedEdlItem:
    return parse_item(item(id, kind, t_start, t_end, params=params))


def test_a_glitch_window_is_the_same_for_the_same_seed_and_place() -> None:
    params = GlitchParams(strength=0.7, seed=5)
    window = glitch_window(params, 60, 15, (540, 960))
    assert window == glitch_window(params, 60, 15, (540, 960))
    assert window != glitch_window(
        params.model_copy(update={"seed": 6}), 60, 15, (540, 960)
    )
    assert window != glitch_window(params, 90, 15, (540, 960))
    assert 0 in window.glitches and len(window.frames) == 15


@pytest.mark.parametrize("seed", range(20))
def test_a_stutter_repeats_a_run_and_never_runs_ahead(seed: int) -> None:
    frames = stutter_frames(15, 1.0, random.Random(seed))
    assert len(frames) == 15
    assert all(shown <= k for k, shown in enumerate(frames))
    start = next(k for k, shown in enumerate(frames) if shown != k)
    repeated = frames[start : start + STUTTER_SIZE]
    assert repeated == frames[start - STUTTER_SIZE : start][: len(repeated)]


def test_short_windows_do_not_stutter() -> None:
    assert stutter_frames(3, 1.0, random.Random(1)) == [0, 1, 2]


@pytest.mark.parametrize("strength", [0.1, 0.5, 1.0])
def test_glitch_frames_stay_inside_the_frame_and_grow_with_strength(
    strength: float,
) -> None:
    window = glitch_window(GlitchParams(strength=strength, seed=1), 0, 30, (540, 960))
    for glitch in window.glitches.values():
        assert 1 <= abs(glitch.split) <= round(540 * 0.02 * strength) + 1
        for top, bottom, slide in glitch.bands:
            assert 0 <= top < bottom <= 960
            assert abs(slide) <= round(540 * 0.15 * strength)


def test_stronger_glitches_glitch_more_frames() -> None:
    def glitched(strength: float) -> int:
        return sum(
            len(
                glitch_window(
                    GlitchParams(strength=strength, seed=s), 0, 30, (540, 960)
                ).glitches
            )
            for s in range(20)
        )

    assert glitched(1.0) > glitched(0.1)


@pytest.mark.parametrize(
    ("offset", "angle", "width", "expected"),
    [
        (8.0, 0.0, 1080, (8, 0)),
        (8.0, 0.0, 540, (4, 0)),
        (8.0, 90.0, 1080, (0, -8)),
        (8.0, 180.0, 1080, (-8, 0)),
        (10.0, -90.0, 1080, (0, 10)),
        (0.5, 0.0, 540, (1, 0)),
        (0.5, 90.0, 540, (0, -1)),
    ],
)
def test_rgb_split_offsets(
    offset: float, angle: float, width: int, expected: tuple[int, int]
) -> None:
    assert split_offsets(offset, angle, width) == expected


def test_an_rgb_split_is_drawn_on_its_window_only() -> None:
    split = typed("rgb_split", 0.5, 1.0, offset_px=16)
    assert glitch_filters([split], CANVAS) == [
        "split[pe_glitch0main][pe_glitch0src];[pe_glitch0src]"
        "trim=start_frame=15:end_frame=30,setpts=PTS-STARTPTS,"
        "format=gbrp,rgbashift=rh=8:rv=0:bh=-8:bv=0,format=yuv420p,"
        "tpad=start=15[pe_glitch0win];[pe_glitch0main][pe_glitch0win]"
        "overlay=eof_action=pass:repeatlast=0:"
        "enable='gte(t,0.483333)*lt(t,0.983333)'"
    ]


def test_glitches_and_glitch_transitions_get_one_window_each() -> None:
    items = [
        typed("transition", 2.0, 2.4, id=3, type="glitch"),
        typed("transition", 3.0, 3.4, id=4, type="crossfade"),
        typed("glitch", 1.0, 1.5, id=5, seed=9),
    ]
    filters = glitch_filters(items, CANVAS)
    assert len(filters) == 2
    assert "trim=start_frame=30:end_frame=45" in filters[0]
    assert "trim=start_frame=60:end_frame=72" in filters[1]
    assert all("geq=r=" in f and "enable='eq(n,0)'" in f for f in filters)
    assert "[pe_glitch1main]" in filters[1]
    assert glitch_filters([typed("glitch", 1.0, 1.01)], CANVAS) == []


def test_every_transition_type_has_an_xfade() -> None:
    types = get_args(TransitionParams.model_fields["type"].annotation)
    # The loop ending is not an xfade (render/loop_end.py).
    assert set(XFADE_OF_TYPE) == set(types) - {"loop"}
    assert XFADE_OF_TYPE["crossfade"] == "fade" and XFADE_OF_TYPE["whip"] == "hblur"


def test_a_transition_is_centred_on_the_cut_at_its_middle_frame() -> None:
    items = [
        typed("transition", 3.0, 3.4, id=2, type="flash"),
        typed("transition", 1.0, 1.4, id=1),
        typed("transition", 2.0, 2.4333, id=3, type="whip"),
        typed("transition", 4.0, 4.03, id=4),
    ]
    windows = transition_windows(items, 30)
    assert windows == [
        TransitionWindow(30, 42, 6, Join("fade", 6, 0.2)),
        TransitionWindow(60, 73, 6, Join("hblur", 6, 0.2)),
        TransitionWindow(90, 102, 6, Join("fadewhite", 6, 0.2)),
    ]
    assert [window.cut for window in windows] == [36, 66, 96]


def test_a_transition_blends_its_window_only() -> None:
    items = [typed("transition", 1.0, 1.4), typed("transition", 3.0, 3.4, id=2)]
    first, second = transition_filters(items, 30)
    assert first == (
        "split[pe_tr0main][pe_tr0src];[pe_tr0src]split[pe_tr0_a][pe_tr0_b];"
        "[pe_tr0_a]trim=start_frame=30:end_frame=36,setpts=PTS-STARTPTS[pe_tr0_ap];"
        "[pe_tr0_b]trim=start_frame=36:end_frame=42,setpts=PTS-STARTPTS[pe_tr0_bp];"
        "[pe_tr0_ap]settb=AVTB,tpad=stop_mode=clone:stop=6[pe_tr0_p0];"
        "[pe_tr0_bp]settb=AVTB,tpad=start_mode=clone:start=6[pe_tr0_p1];"
        "[pe_tr0_p0][pe_tr0_p1]xfade=transition=fade:duration=0.400000"
        ":offset=0.000000,format=yuv420p,tpad=start=30[pe_tr0win];"
        "[pe_tr0main][pe_tr0win]overlay=eof_action=pass:repeatlast=0:"
        "enable='gte(t,0.983333)*lt(t,1.383333)'"
    )
    assert second.startswith("split[pe_tr1main][pe_tr1src];")
    assert "trim=start_frame=96:end_frame=102" in second
    assert transition_filters([typed("glitch", 1.0, 1.4)], 30) == []
    assert transition_filters([typed("transition", 1.0, 1.04)], 30) == []


def test_join_graph_keeps_its_labels_by_default() -> None:
    graph = join_graph(["[a]", "[b]"], [(0.0, 1.0), (1.0, 2.0)], [None], "[out]")
    assert graph == (
        "[a]settb=AVTB[join_p0];[b]settb=AVTB[join_p1];"
        "[join_p0][join_p1]concat=n=2:v=1:a=0[out]"
    )


def textured(seed: int = 3) -> np.ndarray:
    """A 160x200 RGB frame of blurred noise, its channels sharing the
    texture as a picture's do (each a different tint of it)."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, (160, 200)).astype(np.float32)
    texture = cv2.GaussianBlur(noise, (0, 0), 2.0)
    texture = (texture - texture.min()) / (texture.max() - texture.min())
    tints = [(200, 30), (160, 60), (120, 90)]
    return np.stack([texture * a + b for a, b in tints], axis=2).astype(np.uint8)


def test_the_channel_offset_heuristic_finds_a_split() -> None:
    frame = textured()
    split = frame.copy()
    split[:, :, 0] = np.roll(frame[:, :, 0], (2, 5), axis=(0, 1))
    split[:, :, 2] = np.roll(frame[:, :, 2], (-2, -5), axis=(0, 1))
    found = channel_offset(split)
    assert found.red == (5, 2) and found.blue == (-5, -2)
    assert found.is_split and found.split_px == pytest.approx(np.hypot(5, 2))
    plain = channel_offset(frame)
    assert plain.red == (0, 0) and plain.blue == (0, 0) and not plain.is_split
