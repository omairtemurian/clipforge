"""Tests of the genre reframing presets (SPEC-v2 3.3, TASK-82): the table of
layouts and tracking parameters, on synthetic faces and on a synthetic
moving square (the manual tracking API is in tests/api)."""

from pathlib import Path

import pytest
from clipforge.models import (
    CropPlan,
    FaceBox,
    Layout,
    ProcessingSettings,
    ReframePreset,
    SignalList,
    SourceMeta,
)
from clipforge.pipeline.camera_motion import FAST
from clipforge.pipeline.faces import Frame, sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop, replan
from clipforge.pipeline.reframe_presets import DEFAULT, PARAMS, params_for
from clipforge.pipeline.reframe_run import reframe_clip
from clipforge.pipeline.step import META, SIGNALS, SOURCE, write_json
from moving_square import HEIGHT, WIDTH, make_moving_square

PRESETS: list[ReframePreset] = ["podcast-2", "standup", "gaming", "vlog"]
CLIP = ClipSpan(1, 0.0, 4.0)
FRAME = (1280, 720)


@pytest.fixture(scope="module")
def square(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The 4 s moving square video (tests/moving_square)."""
    return make_moving_square(tmp_path_factory.mktemp("manual") / "square.mp4")


def face(center_x: float) -> FaceBox:
    """A 100 px face centered at (center_x, 300)."""
    return FaceBox(x=center_x - 50, y=250, width=100, height=100, score=0.9)


def two_faces(share: float) -> list[list[FaceBox]]:
    """The faces of a 4 s clip's samples: two in share of them, else one."""
    total = len(sample_times(CLIP.start, CLIP.end))
    two = round(share * total)
    return [[face(300), face(900)] if k < two else [face(300)] for k in range(total)]


def jump() -> list[list[FaceBox]]:
    """The faces of a clip's samples: one face that moves from x 300 to
    x 1000 half way."""
    total = len(sample_times(CLIP.start, CLIP.end))
    return [[face(300)] if k < total // 2 else [face(1000)] for k in range(total)]


def plan(preset: ReframePreset | None, faces: list[list[FaceBox]]) -> CropPlan:
    """The 9:16 plan of the 1280x720 clip with these faces and preset."""
    return plan_crop(CLIP, "9:16", FRAME, faces, [], preset=preset)


@pytest.mark.parametrize(
    ("preset", "layout"),
    [
        (None, "fill"),
        ("podcast-2", "split"),
        ("standup", "fill"),
        ("gaming", "fit"),
        ("vlog", "fill"),
    ],
)
def test_a_preset_maps_to_a_layout_when_half_the_samples_have_two_faces(
    preset: ReframePreset | None, layout: Layout
) -> None:
    result = plan(preset, two_faces(0.5))

    assert result.layout == layout
    assert result.preset == preset


def test_the_default_needs_two_faces_in_more_than_60_percent_to_split() -> None:
    assert plan(None, two_faces(0.7)).layout == "split"
    assert plan("podcast-2", two_faces(0.3)).layout == "fill"
    assert plan("podcast-2", two_faces(0.5)).layout == "split"


@pytest.mark.parametrize("preset", ["standup", "gaming", "vlog"])
def test_presets_with_a_fixed_layout_never_split(preset: ReframePreset) -> None:
    assert plan(preset, two_faces(1.0)).layout != "split"


def test_the_presets_table_of_layout_and_tracking_parameters() -> None:
    table = {
        name: (p.layout, p.split_share, p.camera_motion, p.objects)
        for name, p in PARAMS.items()
    }

    assert table == {
        "podcast-2": (None, 0.4, "calm", False),
        "standup": ("fill", 1.0, "fast", False),
        "gaming": ("fit", 1.0, "calm", False),
        "vlog": ("fill", 1.0, "calm", True),
    }
    assert params_for(None) == DEFAULT
    assert DEFAULT.camera_motion == "calm"
    assert [params_for(name) for name in PRESETS] == list(PARAMS.values())


def test_the_project_camera_motion_wins_over_the_presets() -> None:
    assert params_for("standup", "calm").camera_motion == "calm"
    assert params_for(None, "fast").motion == FAST
    assert params_for("vlog", "normal")._replace(camera_motion="calm") == PARAMS["vlog"]


def test_a_standup_window_catches_a_jump_sooner_than_a_vlog_window() -> None:
    frames = jump()
    half = len(frames) // 2

    standup = plan("standup", frames).keyframes[half + 8].x
    vlog = plan("vlog", frames).keyframes[half + 8].x

    assert standup > vlog


def test_a_plan_keeps_its_preset_when_it_is_framed_for_another_aspect() -> None:
    result = replan(plan("gaming", two_faces(0.5)), "1:1", FRAME, [])

    assert (result.aspect, result.layout, result.preset) == ("1:1", "fit", "gaming")
    assert result.camera_motion == "calm"


def source_job(job: Path, video: Path) -> Path:
    """Make job a work directory of the 640x360 4 s video."""
    job.mkdir(parents=True, exist_ok=True)
    (job / SOURCE).write_bytes(video.read_bytes())
    meta = SourceMeta(
        title="square",
        duration=4.0,
        width=WIDTH,
        height=HEIGHT,
        fps=25.0,
        timeframe_start=0.0,
        timeframe_end=4.0,
    )
    write_json(job / META, meta)
    write_json(job / SIGNALS, SignalList([]))
    return job


def no_faces(frame: Frame) -> list[FaceBox]:
    """A face detector that sees nothing."""
    return []


def moved_to(job: Path, preset: ReframePreset | None) -> float:
    """Reframe the clip of job's square video, and return how far, in frame
    widths, the crop center moves between the first and the last sample."""
    path = reframe_clip(job, CLIP, "9:16", no_faces, preset)
    result = CropPlan.model_validate_json(path.read_bytes())
    first, last = result.keyframes[0], result.keyframes[-1]
    return (last.x - first.x) / WIDTH


@pytest.mark.slow
def test_gaming_does_not_chase_a_moving_object_but_the_default_and_vlog_do(
    square: Path, tmp_path: Path
) -> None:
    default = moved_to(source_job(tmp_path / "default", square), None)
    vlog = moved_to(source_job(tmp_path / "vlog", square), "vlog")
    gaming = moved_to(source_job(tmp_path / "gaming", square), "gaming")

    assert default > 0.3
    assert vlog > 0.3
    assert gaming == 0


def test_the_processing_setting_defaults_to_no_preset() -> None:
    assert ProcessingSettings().reframe_preset is None
    assert ProcessingSettings(reframe_preset="vlog").reframe_preset == "vlog"
