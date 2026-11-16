"""Auto zoom-out moments (TASK-198): the rules, hysteresis, minimum length
and maximum share of pipeline/layout_auto on synthetic faces and motion."""

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from clipforge.models import (
    CropKeyframe,
    CropPlan,
    CropWindow,
    FaceBox,
    ProcessingSettings,
    SceneReframe,
)
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.layout_auto import (
    ZoomOut,
    cap_share,
    shot_zoom_outs,
    zoom_out_scenes,
)
from clipforge.pipeline.zoom_out_rules import (
    MotionSample,
    sample_reasons,
    zoom_params,
)
from clipforge.zoom_out_settings import ZoomOutSettings
from pydantic import ValidationError

FRAME = (1280, 720)
FILL = 404
PARAMS = zoom_params("balanced", ZoomOutSettings())
assert PARAMS is not None


def face(center_x: float, size: float = 200, kind: str = "face") -> FaceBox:
    """Return a size px box of kind centered at center_x, 360."""
    half = size / 2
    return FaceBox(
        x=center_x - half, y=360 - half, width=size, height=size, score=0.9, kind=kind
    )


ONE = [face(640)]
APART = [face(213), face(1067)]  # 1054 px: wider than the frame's square
NEAR = [face(440), face(840)]  # 600 px: wider than the fill, inside the square
SMALL = [face(640, size=50)]  # under 0.12 of 720 px


def plan(end: float, faces: Callable[[float], list[FaceBox]]) -> CropPlan:
    """Return the 9:16 plan of a clip of 0 to end seconds whose samples
    see faces(t)."""
    window = CropWindow(width=640, height=360, y=0, xs=[])
    return CropPlan(
        clip_id=1,
        start=0,
        end=end,
        aspect="9:16",
        width=FILL,
        height=720,
        y=0,
        keyframes=[
            CropKeyframe(t=t, x=438, faces=faces(t)) for t in sample_times(0, end)
        ],
        layout="fill",
        split=(window, window),
    )


def between(*spans: tuple[float, float], inside: list[FaceBox], outside=ONE):
    """Return faces(t): inside within any of spans, else outside."""
    return lambda t: inside if any(a <= t < b for a, b in spans) else outside


def zoom_outs(crop: CropPlan, motion: list[MotionSample] | None = None):
    """Return the zoom-out scenes of crop's whole clip as one auto fill
    scene without cuts, as (start, end, layout)."""
    whole = [SceneReframe(start=crop.start, end=crop.end, layout="fill")]
    scenes = zoom_out_scenes(crop, whole, FRAME, [], motion or [], PARAMS)
    return [(s.start, s.end, s.layout) for s in scenes if s.layout != "fill"]


def reasons(faces: list[list[FaceBox]], motion: list[MotionSample] | None = None):
    """Return sample_reasons of samples 0.1 s apart that see faces."""
    keys = [CropKeyframe(t=i / 10, x=0, faces=f) for i, f in enumerate(faces)]
    return sample_reasons(keys, FRAME, FILL, motion or [], PARAMS)


def test_each_rule_names_its_reason_and_whether_it_needs_the_whole_frame() -> None:
    assert reasons([APART, NEAR, SMALL, ONE]) == [
        ("spread", True),
        ("spread", False),
        ("wide", False),
        (None, False),
    ]
    still = [MotionSample(t=0, spread=0.3)]
    assert reasons([[]], [MotionSample(t=0, spread=0.6)]) == [("motion", True)]
    assert reasons([[]], still) == [(None, False)]
    # A person (no face) seen: not motion, even if the frame moves.
    person = [face(640, kind="person")]
    assert reasons([person], [MotionSample(t=0, spread=0.9)]) == [(None, False)]


def test_a_subject_lost_longer_than_lost_s_in_a_shot_that_shows_them() -> None:
    lost = reasons([ONE] * 5 + [[]] * 15 + [ONE] * 5)
    assert [r for r, _ in lost[5:20]] == ["lost"] * 15
    assert {r for r, _ in lost[:5] + lost[20:]} == {None}
    brief = reasons([ONE] * 5 + [[]] * 5 + [ONE] * 5)
    assert {r for r, _ in brief} == {None}
    assert {r for r, _ in reasons([[]] * 30)} == {None}


def test_a_lasting_reason_zooms_out_in_fit_or_square_blur() -> None:
    assert zoom_outs(plan(20, between((5, 10), inside=APART))) == [(5.0, 10.0, "fit")]
    assert zoom_outs(plan(20, between((5, 10), inside=NEAR))) == [
        (5.0, 10.0, "square_blur")
    ]
    assert zoom_outs(plan(20, between((5, 10), inside=SMALL))) == [
        (5.0, 10.0, "square_blur")
    ]
    motion = [MotionSample(t=t / 4, spread=0.8) for t in range(80)]
    assert zoom_outs(plan(20, between((5, 10), inside=[])), motion) == [
        (5.0, 10.0, "fit")
    ]


def test_one_framed_speaker_and_an_off_intensity_never_zoom_out() -> None:
    assert zoom_outs(plan(20, lambda t: ONE)) == []
    assert zoom_params("off", ZoomOutSettings()) is None


def test_hysteresis_does_not_flap_on_alternating_samples() -> None:
    flicker = plan(20, lambda t: APART if round(t * 10) % 2 else ONE)
    assert zoom_outs(flicker) == []
    # Brief gaps inside a zoom-out do not end it.
    gappy = plan(20, lambda t: ONE if 7 <= t < 7.3 or t < 4 or t >= 10 else APART)
    assert zoom_outs(gappy) == [(4.0, 10.0, "fit")]


def test_zoom_outs_last_at_least_min_segment_s() -> None:
    assert zoom_outs(plan(20, between((5, 7), inside=APART))) == []
    for start, end, _ in zoom_outs(plan(20, between((5, 8), inside=APART))):
        assert end - start >= PARAMS.min_segment_s


def test_zoom_outs_take_at_most_max_share_of_the_clip() -> None:
    crop = plan(30, between((3, 8), (12, 17), (22, 27), inside=APART))
    found = zoom_outs(crop)
    assert found == [(3.0, 8.0, "fit"), (12.0, 17.0, "fit")]
    assert sum(end - start for start, end, _ in found) <= 0.4 * 30


def test_the_cap_keeps_the_strongest_then_the_longest() -> None:
    weak = ZoomOut(0, 6, "fit", 0.6)
    strong = ZoomOut(10, 13, "fit", 1.0)
    long = ZoomOut(20, 25, "fit", 1.0)
    assert cap_share([weak, strong, long], 8) == [strong, long]
    assert cap_share([weak, strong, long], 4) == [strong]


def test_intensity_scales_the_thresholds() -> None:
    cfg = ZoomOutSettings()
    subtle, frequent = zoom_params("subtle", cfg), zoom_params("frequent", cfg)
    assert subtle is not None and frequent is not None
    assert (subtle.max_share, subtle.wide_face_height) == pytest.approx((0.2, 0.06))
    assert (subtle.lost_s, subtle.motion_spread) == pytest.approx((2.0, 0.75))
    assert (frequent.max_share, frequent.lost_s) == pytest.approx((0.6, 1 / 1.5))
    assert frequent.motion_spread == pytest.approx(0.25)


def test_only_auto_fill_scenes_zoom_out_and_shots_bound_them() -> None:
    crop = plan(20, between((5, 10), inside=APART))
    scenes = [
        SceneReframe(start=0, end=8, layout="fill", mode="fixed"),
        SceneReframe(start=8, end=20, layout="fill"),
    ]
    assert zoom_out_scenes(crop, scenes, FRAME, [], [], PARAMS) == scenes
    whole = [SceneReframe(start=0, end=20, layout="fill")]
    cut = zoom_out_scenes(crop, whole, FRAME, [7.0], [], PARAMS)
    assert [(s.start, s.end, s.layout) for s in cut] == [
        (0, 7.0, "fill"),
        (7.0, 10.0, "fit"),
        (10.0, 20, "fill"),
    ]


def test_shot_zoom_outs_are_inside_their_shot() -> None:
    shot = SceneReframe(start=2, end=6, layout="fill")
    keys = [CropKeyframe(t=2 + i / 10, x=0, faces=APART) for i in range(40)]
    found = shot_zoom_outs(
        shot, keys, sample_reasons(keys, FRAME, FILL, [], PARAMS), PARAMS
    )
    assert found == [ZoomOut(2, 6, "fit", 1.0)]


def test_projects_zoom_out_balanced_and_config_yaml_has_the_defaults() -> None:
    assert ProcessingSettings().zoom_out_moments == "balanced"
    assert ProcessingSettings(zoom_out_moments="off").zoom_out_moments == "off"
    with pytest.raises(ValidationError):
        ProcessingSettings(zoom_out_moments="always")  # type: ignore[arg-type]
    root = Path(__file__).resolve().parents[3] / "config.yaml"
    block = yaml.safe_load(root.read_text(encoding="utf-8"))["zoom_out"]
    assert ZoomOutSettings(**block) == ZoomOutSettings()
