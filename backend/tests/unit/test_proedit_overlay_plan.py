"""Tests of overlay placement and frames (SPEC-v3 1.3/3.3, TASK-212)."""

from pathlib import Path
from typing import Any

import pytest
from clipforge.proedit.edl import OverlayItem, parse_item
from clipforge.proedit.render.canvas import Box, Camera, Canvas
from clipforge.proedit.render.overlay import (
    FRAME_PATTERN,
    Spot,
    bounds,
    item_frames,
    overlay_filters,
    overlay_problems,
)
from clipforge.proedit.render.overlay_plan import (
    anchor_boxes,
    animated,
    placements,
    seen,
)
from edl_fakes import item

FPS = 30
SIZE = (540, 960)
FACE = Box(0.4, 0.3, 0.6, 0.4)


def overlay(params: dict[str, Any], t_start: float = 1.0, id: int = 1) -> OverlayItem:
    """An overlay item of params over t_start to t_start + 1 s."""
    found = parse_item(item(id, "overlay", t_start, t_start + 1.0, params=params))
    assert isinstance(found, OverlayItem)
    return found


def test_a_screen_overlay_is_placed_on_the_frame() -> None:
    places = placements(
        overlay({"asset": "skull", "x": 0.25, "y": 0.5, "animation": "none"}),
        Canvas(FPS, SIZE),
    )
    assert len(places) == 30
    assert {(p.x, p.y, p.width, p.alpha) for p in places} == {
        (135.0, 480.0, 162.0, 1.0)
    }


def test_a_face_overlay_follows_and_scales_with_the_face() -> None:
    faces = [FACE] * 45 + [Box(0.2, 0.5, 0.3, 0.55)] * 30
    canvas = Canvas(FPS, SIZE, faces)
    params = {"asset": "circle", "anchor": "face", "scale": 1.5, "y": 0.0}
    params["animation"] = "none"
    places = placements(overlay(params), canvas)
    first, last = places[0], places[-1]
    assert (first.x, first.y) == pytest.approx((0.5 * 540, 0.3 * 960))
    assert first.width == pytest.approx(1.5 * 0.2 * 540)
    assert (last.x, last.y) == pytest.approx((0.25 * 540, 0.5 * 960))
    assert last.width == pytest.approx(1.5 * 0.1 * 540)


def test_an_object_overlay_follows_the_object() -> None:
    canvas = Canvas(
        FPS, SIZE, [FACE] * 60, [None] * 30 + [Box(0.0, 0.0, 0.5, 0.5)] * 30
    )
    places = placements(overlay({"asset": "arrow", "anchor": "object"}), canvas)
    assert (places[0].x, places[0].y) == pytest.approx((135.0, 240.0))


def test_frames_without_a_box_take_the_nearest_box_of_the_window() -> None:
    other = Box(0.1, 0.1, 0.2, 0.2)
    faces = [None] * 32 + [FACE] * 3 + [None] * 10 + [other] * 15
    boxes = anchor_boxes(
        overlay({"asset": "circle", "anchor": "face"}), Canvas(FPS, SIZE, faces)
    )
    assert boxes is not None
    assert boxes[:5] == [FACE] * 5
    assert boxes[9] == FACE and boxes[10] == other
    assert boxes[-1] == other


def test_an_anchor_without_any_box_falls_back_to_the_screen() -> None:
    item = overlay({"asset": "circle", "anchor": "object", "x": 0.5, "y": 0.5})
    assert anchor_boxes(item, Canvas(FPS, SIZE, [FACE] * 60)) is None
    assert placements(item, Canvas(FPS, SIZE))[0].x == 270.0


def test_a_box_is_seen_through_the_zoom_stages_camera() -> None:
    # Scale 2 centered: the 1080x1920 frame cropped at (270, 480).
    box = seen(Box(0.5, 0.5, 0.6, 0.6), Camera(2.0, 0.5, 0.5), SIZE)
    assert (box.left, box.top) == pytest.approx((0.5, 0.5))
    assert (box.right, box.bottom) == pytest.approx((0.7, 0.7))
    assert seen(FACE, None, SIZE) == FACE


def test_an_anchored_overlay_uses_the_frames_camera() -> None:
    faces = [Box(0.5, 0.5, 0.6, 0.6)] * 60
    canvas = Canvas(FPS, SIZE, faces, cameras={31: Camera(2.0, 0.5, 0.5)})
    params = {"asset": "circle", "anchor": "face", "animation": "none"}
    places = placements(overlay(params), canvas)
    assert places[0].width == pytest.approx(0.3 * 0.1 * 540)
    assert places[1].width == pytest.approx(0.3 * 0.2 * 540)
    assert places[1].x == pytest.approx(0.6 * 540)


@pytest.mark.parametrize(
    ("animation", "k", "expected"),
    [
        ("none", 0, (1.0, 1.0, 0.0)),
        ("fade", 0, (1.0, 1 / 6, 0.0)),
        ("fade", 10, (1.0, 1.0, 0.0)),
        ("fade", 29, (1.0, 1 / 6, 0.0)),
        ("pop", 5, (1.0, 1.0, 0.0)),
        ("bounce", 11, (1.0, 1.0, 0.0)),
        ("slide", 0, (1.0, 1.0, 0.15 * (1 - 0.0185185))),
        ("slide", 5, (1.0, 1.0, 0.0)),
    ],
)
def test_animations(animation: Any, k: int, expected: tuple[float, ...]) -> None:
    assert animated(animation, k, 30, FPS) == pytest.approx(expected, abs=1e-4)


def test_a_pop_overshoots_its_size_before_settling() -> None:
    sizes = [animated("pop", k, 30, FPS)[0] for k in range(6)]
    assert sizes[0] < sizes[1] < 1.0 < max(sizes)


def test_bounds_hold_every_shown_spot_on_even_pixels_inside_the_frame() -> None:
    found = [Spot(-5, 11, 20, 20, 1.0), Spot(31, 3, 9, 9, 0.5), Spot(0, 0, 0, 0, 1.0)]
    assert bounds(found, (36, 64)) == (0, 2, 36, 32)
    assert bounds([Spot(1, 1, 5, 5, 0.0)], SIZE) is None
    assert bounds([Spot(600, 10, 5, 5, 1.0)], SIZE) is None


def test_problems_name_the_undrawable_overlays() -> None:
    items = [overlay({"asset": "skull"}), overlay({"asset": "emoji:a"}, id=2)]
    assert overlay_problems(items) == [
        "item 2 (overlay): the emoji font has no glyph for U+0061 of 'emoji:a'"
    ]


def test_frames_are_written_once_per_drawing(data_dir: Path) -> None:
    item = overlay({"asset": "skull", "x": 0.5, "y": 0.5, "animation": "fade"})
    frames = item_frames(item, Canvas(FPS, SIZE))
    assert frames is not None
    files = sorted(frames.folder.iterdir())
    assert [f.name for f in files] == [FRAME_PATTERN % n for n in range(30)]
    assert frames.width % 2 == frames.height % 2 == frames.x % 2 == 0
    stamp = files[0].stat().st_mtime_ns
    again = item_frames(item, Canvas(FPS, SIZE))
    assert again == frames
    assert files[0].stat().st_mtime_ns == stamp
    turned = overlay({"asset": "skull", "rotation_deg": 30})
    assert item_frames(turned, Canvas(FPS, SIZE)).folder != frames.folder  # type: ignore[union-attr]


def test_the_filter_draws_the_frames_on_the_window(data_dir: Path) -> None:
    (chain,) = overlay_filters([overlay({"asset": "circle"}, id=7)], Canvas(FPS, SIZE))
    assert chain.startswith("format=pix_fmts=yuv420p:color_ranges=tv[ov7main];movie=")
    assert ":f=image2,settb=expr=1/30,setpts=N+30,format=rgba[ov7img];" in chain
    assert chain.endswith(
        "eof_action=pass:repeatlast=0:enable='gte(t,0.983333)*lt(t,1.983333)'"
    )
    assert str(data_dir) in chain.replace("\\", "")


def test_an_overlay_off_the_frame_draws_nothing(data_dir: Path) -> None:
    # The face is out of the zoomed-in view.
    item = overlay({"asset": "circle", "anchor": "face", "scale": 0.5})
    cameras = {frame: Camera(2.0, 0.75, 0.75) for frame in range(30, 60)}
    canvas = Canvas(FPS, SIZE, [Box(0.0, 0.0, 0.05, 0.05)] * 60, cameras=cameras)
    assert overlay_filters([item], canvas) == []
