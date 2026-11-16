"""Unit tests of the Pro Edit shake, speed ramps and slow motion
(proedit/render/motion_time.py, TASK-210): the seeded shake path and its
cameras (room to move, face kept in, zooms kept), the speeds and content
times of slowmo and speed_ramp windows, when each clip frame plays and the
filters that play them. The frames are tested with ffmpeg in
tests/pipeline/test_proedit_render_speed.py."""

from typing import Any

import pytest
from clipforge.models import EdlKind
from clipforge.proedit.edl import (
    ShakeItem,
    SlowmoItem,
    SpeedRampItem,
    TypedEdlItem,
    parse_item,
)
from clipforge.proedit.render.canvas import Box, Camera, Canvas
from clipforge.proedit.render.motion import cameras_of
from clipforge.proedit.render.motion_time import (
    SHAKE_MAX,
    SPEED_MIN,
    camera_filters,
    content_frames,
    content_times,
    play_times,
    pts_steps,
    shake_path,
    shaken,
    speeds,
    time_filters,
)
from edl_fakes import item

CANVAS = Canvas(30, (540, 960))


def typed(
    kind: EdlKind,
    params: dict[str, Any],
    t_start: float = 1.0,
    t_end: float = 2.0,
    id: int = 1,
) -> TypedEdlItem:
    return parse_item(item(id, kind, t_start, t_end, params=params))


def shake(t_start: float = 1.0, **params: Any) -> ShakeItem:
    found = typed("shake", params, t_start, t_start + 1.0)
    assert isinstance(found, ShakeItem)
    return found


def slowmo(speed: float, ramp_s: float, t_end: float = 2.0) -> SlowmoItem:
    found = typed("slowmo", {"speed": speed, "ramp_s": ramp_s}, 1.0, t_end)
    assert isinstance(found, SlowmoItem)
    return found


def ramp(speed_from: float, speed_to: float, ease: str = "linear") -> SpeedRampItem:
    params = {"speed_from": speed_from, "speed_to": speed_to, "ease": ease}
    found = typed("speed_ramp", params)
    assert isinstance(found, SpeedRampItem)
    return found


def test_a_shake_path_is_seeded_bounded_and_turns_back() -> None:
    path = shake_path(shake(strength=0.5, frequency_hz=15, seed=3), 30)
    assert sorted(path) == list(range(30, 60))
    assert path == shake_path(shake(strength=0.5, frequency_hz=15, seed=3), 30)
    assert path != shake_path(shake(strength=0.5, frequency_hz=15, seed=4), 30)
    amplitude = 0.5 * SHAKE_MAX
    xs = [x for x, _ in path.values()]
    assert all(abs(x) <= amplitude + 1e-9 for x, _ in path.values())
    assert all(abs(y) <= amplitude * 0.6 + 1e-9 for _, y in path.values())
    # At 15 Hz the knots fall on every frame: the picture jolts to and fro.
    assert all(a * b < 0 for a, b in zip(xs, xs[1:], strict=False))
    assert min(abs(x) for x in xs) >= amplitude * 0.5 - 1e-9


def test_a_shake_zooms_in_just_enough_and_stays_in_the_frame() -> None:
    found = shaken({}, [shake(strength=1.0, seed=1)], CANVAS)
    assert sorted(found) == list(range(30, 60))
    for camera in found.values():
        assert camera.scale == pytest.approx(1 + 2 * SHAKE_MAX)
        half = 0.5 / camera.scale
        assert half - 1e-9 <= camera.x <= 1 - half + 1e-9
        assert half - 1e-9 <= camera.y <= 1 - half + 1e-9
    assert len({round(camera.x, 6) for camera in found.values()}) > 10


def test_a_shake_on_a_zoom_keeps_the_zoom_and_the_face() -> None:
    face = Box(0.80, 0.4, 0.95, 0.5)
    canvas = Canvas(30, (540, 960), [face] * 90)
    punch = typed("zoom_punch", {"scale": 1.3}, 1.0, 2.0, id=2)
    zoomed = cameras_of([punch], canvas)
    found = shaken(zoomed, [shake(strength=1.0, seed=5)], canvas)
    for frame, camera in found.items():
        assert camera.scale == pytest.approx(zoomed[frame].scale)
        half = 0.5 / camera.scale
        assert camera.x - half <= face.left and face.right <= camera.x + half
        assert camera.y - half <= face.top and face.bottom <= camera.y + half
    assert shaken(zoomed, [], canvas) == zoomed


def test_camera_filters_draw_zooms_and_shakes() -> None:
    assert camera_filters([], CANVAS) == []
    filters = camera_filters([shake()], CANVAS)
    assert [f.split("=")[0] for f in filters] == ["scale", "crop", "setsar"]


def test_slow_motion_eases_down_and_back_up() -> None:
    assert speeds(slowmo(0.5, 0.0), 30, 30) == [0.5] * 30
    eased = speeds(slowmo(0.4, 0.2), 30, 30)
    assert eased[0] > 0.9 and eased[-1] > 0.9
    assert eased[6:24] == pytest.approx([0.4] * 18)
    assert eased[:6] == sorted(eased[:6], reverse=True)
    # A ramp longer than half the window takes half of it.
    assert min(speeds(slowmo(0.5, 1.0, t_end=1.4), 12, 30)) > 0.5


def test_a_speed_ramp_eases_from_one_speed_to_the_other() -> None:
    linear = speeds(ramp(1.0, 0.4), 30, 30)
    assert linear[0] == pytest.approx(1 - 0.6 / 60)
    assert linear[-1] == pytest.approx(0.4 + 0.6 / 60)
    assert speeds(ramp(1.0, 3.0), 30, 30)[-1] > 2.9
    # elastic overshoots: the speed never goes below SPEED_MIN.
    assert min(speeds(ramp(1.0, 0.1, "elastic"), 30, 30)) == SPEED_MIN


def test_content_times_add_up_the_speeds() -> None:
    times = content_times(slowmo(0.5, 0.0), 30)
    assert len(times) == 31
    assert times[0] == 0.0 and times[-1] == pytest.approx(0.5)
    assert content_frames([slowmo(0.5, 0.0)], 30)[31] == pytest.approx(30.5)
    assert content_frames([shake()], 30) == {}


def test_each_clip_frame_plays_where_the_speeds_put_it() -> None:
    times = content_times(slowmo(0.5, 0.0), 30)
    played = play_times(times, 30, 18)
    assert played == pytest.approx([2 * i / 30 for i in range(18)])
    fast = content_times(ramp(2.0, 2.0 + 1e-9), 30)
    assert play_times(fast, 30, 4) == pytest.approx([i / 60 for i in range(4)])


def test_pts_steps_count_microseconds_by_frame() -> None:
    steps = "(0)+((50000*gte(N,1))+(50000*gte(N,2)))"
    assert pts_steps([0.0, 0.05, 0.1]) == steps
    # A frame on the same tick as the last adds no term.
    assert pts_steps([0.0, 0.0, 0.1]) == "(0)+(100000*gte(N,2))"


def test_time_filters_play_the_window_over_the_clip() -> None:
    filters = time_filters([slowmo(0.5, 0.0)], 30)
    assert len(filters) == 1
    chain = filters[0]
    assert chain.startswith("split[pe_timemain0][pe_timesrc0];[pe_timesrc0]")
    assert "trim=start_frame=30:end_frame=49," in chain
    assert "settb=1/1000000,setpts='" in chain
    assert "minterpolate=fps=30:mi_mode=mci,trim=end_frame=30,tpad=start=30" in chain
    assert chain.endswith(
        "[pe_timemain0][pe_timewin0]overlay=eof_action=pass:repeatlast=0:"
        "enable='gte(t,0.983333)*lt(t,1.983333)'"
    )
    two = time_filters([ramp(1.0, 0.5), typed("slowmo", {}, 3.0, 4.0, id=2)], 30)
    assert "[pe_timewin1]" in two[1]
    assert time_filters([shake()], 30) == []


def test_frames_after_a_shake_are_not_moved() -> None:
    found = shaken({70: Camera(1.2, 0.5, 0.5)}, [shake()], CANVAS)
    assert found[70] == Camera(1.2, 0.5, 0.5)
    assert 60 not in found
