"""Unit tests of the Pro Edit zoom and pan (SPEC-v3 3.3, TASK-209): the
easing curves, the planned scale of each kind, the face-safe cap and
center, the whole-pixel crops (a randomized check that the subject's face
is inside every zoomed frame) and the filters' text. The frames themselves
are measured with ffmpeg in tests/pipeline/test_proedit_render_motion.py."""

import random
from typing import Any

import pytest
from clipforge.models import EdlKind
from clipforge.proedit.edl import TypedEdlItem, parse_item
from clipforge.proedit.render.canvas import Box, Camera, Canvas
from clipforge.proedit.render.easing import ease
from clipforge.proedit.render.motion import (
    FACE_MARGIN,
    Crop,
    cameras_of,
    crop_of,
    crops_of,
    fitted,
    motion_filters,
    safe_axis,
)
from edl_fakes import item

SIZE = (540, 960)
EASES = ("linear", "ease_in_out", "back", "elastic")


def typed(
    kind: EdlKind, t_start: float, t_end: float, id: int = 1, **params: Any
) -> TypedEdlItem:
    return parse_item(item(id, kind, t_start, t_end, params=params))


def scales(
    items: list[TypedEdlItem], faces: list[Box | None] | None = None
) -> dict[int, float]:
    canvas = Canvas(30, SIZE, faces or [])
    return {n: round(c.scale, 4) for n, c in cameras_of(items, canvas).items()}


@pytest.mark.parametrize(
    ("name", "p", "expected"),
    [
        ("linear", 0.25, 0.25),
        ("ease_in_out", 0.25, 0.0625),
        ("ease_in_out", 0.5, 0.5),
        ("ease_in_out", 0.75, 0.9375),
        ("back", 0.5, 1.0877),
        ("back", 0.8, 1.0465),
        ("elastic", 0.2, 1.125),
        ("elastic", 0.5, 1.0156),
    ],
)
def test_easing_curves(name: Any, p: float, expected: float) -> None:
    assert ease(name, p) == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize("name", EASES)
def test_every_curve_starts_at_0_and_ends_at_1(name: Any) -> None:
    assert ease(name, 0.0) == pytest.approx(0.0, abs=1e-9)
    assert ease(name, 1.0) == pytest.approx(1.0, abs=1e-9)
    assert ease(name, -1.0) == ease(name, 0.0) and ease(name, 2.0) == ease(name, 1.0)


def test_a_punch_is_instant_or_eased_over_its_first_frames() -> None:
    instant = typed("zoom_punch", 1.0, 1.2, scale=1.25, center="frame")
    assert scales([instant]) == {n: 1.25 for n in range(30, 36)}
    eased = typed("zoom_punch", 1.0, 1.2, scale=1.3, ease_frames=4, ease="linear")
    assert scales([eased]) == {
        30: 1.075,
        31: 1.15,
        32: 1.225,
        **{n: 1.3 for n in range(33, 36)},
    }


def test_push_and_reveal_ease_from_their_first_to_their_last_frame() -> None:
    push = typed("zoom_push", 0.0, 1.0, scale_from=1.0, scale_to=1.12)
    reveal = typed("zoom_out_reveal", 2.0, 2.5, id=2, ease="linear")
    found = scales([push, reveal])
    assert (found[0], found[29]) == (1.0, 1.12)
    assert found[7] == pytest.approx(1 + 0.12 * ease("ease_in_out", 7 / 29), abs=1e-4)
    assert [found[n] for n in (60, 67, 74)] == [1.2, 1.1, 1.0]
    assert 75 not in found


def test_a_punch_right_after_a_push_starts_from_its_scale() -> None:
    push = typed("zoom_push", 0.0, 1.0, scale_to=1.12, center="frame")
    punch = typed("zoom_punch", 1.0, 1.5, id=2, scale=1.3, ease_frames=2, ease="linear")
    found = scales([punch, push])
    assert (found[29], found[30], found[31]) == (1.12, 1.21, 1.3)


def test_overshoot_goes_past_the_end_but_never_below_1() -> None:
    punch = typed("zoom_punch", 0.0, 0.5, scale=1.2, ease_frames=4, ease="elastic")
    assert max(scales([punch]).values()) > 1.2
    reveal = typed("zoom_out_reveal", 0.0, 1.0, scale_from=1.3, ease="back")
    found = scales([reveal])
    assert min(found.values()) == 1.0 and found[29] == 1.0


def test_a_pan_moves_the_center_at_its_scale() -> None:
    pan = typed(
        "pan",
        0.0,
        1.0,
        scale=1.25,
        from_x=0.3,
        from_y=0.5,
        to_x=0.7,
        to_y=0.45,
        ease="linear",
    )
    cameras = cameras_of([pan], Canvas(30, SIZE))
    first, last, middle = cameras[0], cameras[29], cameras[15]
    assert first.scale == 1.25 and first.y == 0.5
    assert first.x == pytest.approx(0.4)
    assert last.x == pytest.approx(0.6) and last.y == pytest.approx(0.45)
    assert middle.x == pytest.approx(0.3 + 0.4 * 15 / 29)


def test_a_face_too_big_for_the_zoom_tones_it_down() -> None:
    big = Box(0.2, 0.3, 0.9, 0.5)
    fit = (1 - 2 * FACE_MARGIN) / 0.7
    assert fitted([1.0, 1.3, 1.6], [big, None, big]) == pytest.approx(
        [1.0, 1 + (fit - 1) / 2, fit]
    )
    assert fitted([1.2, 1.3], [Box(0, 0, 1, 0.5)]) == [1.0, 1.0]
    assert fitted([1.2, 1.3], [Box(0.4, 0.4, 0.5, 0.5), None]) == [1.2, 1.3]


def test_the_window_moves_the_least_that_keeps_the_face_in() -> None:
    margin = FACE_MARGIN / 1.25
    assert safe_axis(0.5, 1.25, (0.8, 0.95)) == pytest.approx(0.95 - 0.4 + margin)
    assert safe_axis(0.5, 1.25, (0.45, 0.55)) == 0.5
    assert safe_axis(0.5, 1.25, (0.9, 1.0)) == pytest.approx(0.6)
    assert safe_axis(0.05, 1.25, None) == pytest.approx(0.4)


def test_a_frame_centered_punch_follows_a_face_near_the_edge() -> None:
    face = Box(0.82, 0.4, 0.97, 0.5)
    punch = typed("zoom_punch", 0.0, 0.2, scale=1.3, center="frame")
    crop = crops_of([punch], Canvas(30, SIZE, [face] * 6))[0]
    assert crop == Crop(702, 1248, 158, 144)
    assert face.right * crop.width <= crop.x + SIZE[0]
    centered = crop_of(Camera(1.3, 0.5, 0.5), SIZE)
    assert face.right * centered.width > centered.x + SIZE[0]


def random_item(rng: random.Random, start: float, id: int) -> TypedEdlItem:
    end = start + rng.choice([0.2, 0.5, 1.0])
    kind = rng.choice(["zoom_punch", "zoom_push", "zoom_out_reveal", "pan"])
    params: dict[str, Any] = {"ease": rng.choice(EASES)}
    if kind == "pan":
        params |= {k: rng.random() for k in ("from_x", "from_y", "to_x", "to_y")}
        params["scale"] = rng.uniform(1.0, 2.0)
    else:
        params["center"] = rng.choice(["face", "frame"])
    if kind == "zoom_punch":
        params |= {"scale": rng.uniform(1.1, 1.3), "ease_frames": rng.choice([0, 3])}
    if kind == "zoom_push":
        params |= {"scale_from": 1.0, "scale_to": rng.uniform(1.05, 1.5)}
    if kind == "zoom_out_reveal":
        params |= {"scale_from": rng.uniform(1.1, 1.5), "scale_to": 1.0}
    return typed(kind, start, end, id=id, **params)  # type: ignore[arg-type]


def random_faces(rng: random.Random, count: int) -> list[Box | None]:
    width, height = rng.uniform(0.05, 0.95), rng.uniform(0.03, 0.6)
    x, y = rng.uniform(-0.1, 1.0 - width / 2), rng.uniform(0.0, 1.0 - height)
    step = rng.uniform(-0.01, 0.01)
    faces: list[Box | None] = []
    for n in range(count):
        left = x + step * n
        box = Box(max(left, 0.0), y, min(left + width, 1.0), min(y + height, 1.0))
        hidden = box.width <= 0 or rng.random() < 0.05
        faces.append(None if hidden else box)
    return faces


@pytest.mark.parametrize("seed", range(40))
def test_the_face_is_inside_every_zoomed_frame(seed: int) -> None:
    rng = random.Random(seed)
    items = [random_item(rng, 0.0, 1), random_item(rng, 1.0, 2)]
    items.append(random_item(rng, 2.0, 3))
    faces = random_faces(rng, 120)
    canvas = Canvas(30, SIZE, faces)
    cameras = cameras_of(items, canvas)
    assert cameras
    for frame, camera in cameras.items():
        crop = crop_of(camera, SIZE)
        assert crop.width >= SIZE[0] and crop.height >= SIZE[1]
        assert 0 <= crop.x <= crop.width - SIZE[0]
        assert 0 <= crop.y <= crop.height - SIZE[1]
        assert crop.x % 2 == crop.y % 2 == crop.width % 2 == crop.height % 2 == 0
        face = faces[frame]
        if face is None:
            continue
        assert crop.x <= face.left * crop.width + 1e-6
        assert face.right * crop.width <= crop.x + SIZE[0] + 1e-6
        assert crop.y <= face.top * crop.height + 1e-6
        assert face.bottom * crop.height <= crop.y + SIZE[1] + 1e-6


def test_no_zoom_or_pan_draws_nothing() -> None:
    flash = typed("flash", 0.0, 0.5)
    assert motion_filters([flash], Canvas(30, SIZE)) == []


def test_the_filters_step_the_numbers_at_each_frame() -> None:
    punch = typed("zoom_punch", 0.2, 0.4, scale=1.2, center="frame")
    filters = motion_filters([punch], Canvas(10, (100, 200)))
    up, down = "gte(t,0.150000)", "gte(t,0.350000)"
    assert filters == [
        f"scale=w='(100)+((20*{up})+(-20*{down}))'"
        f":h='(200)+((40*{up})+(-40*{down}))':eval=frame",
        f"crop=w=100:h=200:x='(0)+((10*{up})+(-10*{down}))'"
        f":y='(0)+((20*{up})+(-20*{down}))'",
        "setsar=1",
    ]
