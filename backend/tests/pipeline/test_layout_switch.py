"""Tests of dynamic layout switching (SPEC-v2 3.3, pipeline/layout_switch):
the layout of a segment by who is seen in it, the segments of a clip by
its scene cuts and speaker count, the zoom of a clip framed scene by scene,
and a clip rendered with ffmpeg in several layouts one after another."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import FaceBox, ReframePreset, SceneReframe, ZoomKeyframe
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.layout_switch import (
    main_layout,
    segment_layout,
    switch_scenes,
)
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.reframe_presets import params_for
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.scene_graph import ScenePart
from clipforge.pipeline.zoom_graph import framing_at, zoom_filter
from frames import Pixels, frame_at

FRAME = (1280, 720)
# The fill window of 9:16 in a 1280x720 frame is 404 px wide; of 16:9, all.
TALL_FILL, WIDE_FILL = 404, 1280
RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)


def face(center_x: float, kind: str = "face", size: float = 100) -> FaceBox:
    """Return a size px box of kind centered at center_x, 360."""
    half = size / 2
    return FaceBox(
        x=center_x - half, y=360 - half, width=size, height=size, score=0.9, kind=kind
    )


ONE, TWO = [face(640)], [face(213), face(1067)]
THREE = [face(213), face(640), face(1067)]


def faces_by_time(clip: ClipSpan, at: dict[tuple[float, float], list[FaceBox]]):
    """Return the faces of each sample of clip: those of the span of at
    (start, end seconds) that holds its time, else none."""
    return [
        next((found for (a, b), found in at.items() if a <= t < b), [])
        for t in sample_times(clip.start, clip.end)
    ]


@pytest.mark.parametrize(
    ("samples", "fill", "preset", "expected"),
    [
        ([[]] * 10, TALL_FILL, None, "fit"),
        ([ONE] * 10, TALL_FILL, None, "fill"),
        ([[face(640, "person")]] * 10, TALL_FILL, None, "fill"),
        ([[face(640, "object")]] * 10, TALL_FILL, None, "fill"),
        ([TWO] * 10, TALL_FILL, None, "split"),
        ([THREE] * 10, TALL_FILL, None, "grid"),
        # Both faces fit in a 16:9 window: no split or grid.
        ([TWO] * 10, WIDE_FILL, None, "fill"),
        ([THREE] * 10, WIDE_FILL, None, "fill"),
        # Two faces in 6 of 10 samples: more than podcast-2's 0.4 only.
        ([TWO] * 6 + [ONE] * 4, TALL_FILL, None, "fill"),
        ([TWO] * 6 + [ONE] * 4, TALL_FILL, "podcast-2", "split"),
        # Someone seen in half the samples is enough.
        ([ONE] * 5 + [[]] * 5, TALL_FILL, None, "fill"),
        ([ONE] * 4 + [[]] * 6, TALL_FILL, None, "fit"),
        ([ONE] * 10, TALL_FILL, "gaming", "screenshare"),
        ([[]] * 10, TALL_FILL, "gaming", "fit"),
        ([TWO] * 10, TALL_FILL, "standup", "fill"),
        ([[]] * 10, TALL_FILL, "vlog", "fill"),
        ([], TALL_FILL, None, "fill"),
    ],
)
def test_a_segments_layout_follows_who_is_seen(
    samples: list[list[FaceBox]],
    fill: int,
    preset: ReframePreset | None,
    expected: str,
) -> None:
    layout = segment_layout(samples, FRAME[0], fill, params_for(preset))

    assert layout == expected


def test_scenes_switch_at_cuts_and_lasting_speaker_changes() -> None:
    clip = ClipSpan(1, 0.0, 12.0)
    # One speaker, then two; after the cut nobody, but for a 0.6 s blip.
    faces = faces_by_time(clip, {(0, 3): ONE, (3, 6): TWO, (8, 8.6): TWO})
    plan = plan_crop(clip, "9:16", FRAME, faces, [6.0])

    scenes = switch_scenes(plan, clip.start, clip.end, FRAME[0], [6.0])

    assert [(s.start, s.end, s.layout, s.mode) for s in scenes] == [
        (0.0, 3.0, "fill", "auto"),
        (3.0, 6.0, "split", "auto"),
        (6.0, 12.0, "fit", "auto"),
    ]
    assert main_layout(scenes) == "fit"
    assert switch_scenes(plan, clip.start, clip.end, FRAME[0], [6.0]) == scenes


def test_short_runs_join_their_longer_neighbour() -> None:
    clip = ClipSpan(1, 10.0, 20.0)
    faces = faces_by_time(
        clip,
        {(10, 11): TWO, (11, 14): ONE, (14, 15.5): THREE, (15.5, 20): THREE},
    )
    plan = plan_crop(clip, "9:16", FRAME, faces, [])

    scenes = switch_scenes(plan, clip.start, clip.end, FRAME[0], [])

    assert [(s.start, s.end, s.layout) for s in scenes] == [
        (10.0, 14.0, "fill"),
        (14.0, 20.0, "grid"),
    ]


def test_one_layout_throughout_is_one_scene_per_shot() -> None:
    clip = ClipSpan(1, 0.0, 8.0)
    plan = plan_crop(clip, "9:16", FRAME, faces_by_time(clip, {(0, 8): TWO}), [4])

    scenes = switch_scenes(plan, clip.start, clip.end, FRAME[0], [4.0, 30.0])

    assert [(s.start, s.end, s.layout) for s in scenes] == [
        (0.0, 4.0, "split"),
        (4.0, 8.0, "split"),
    ]
    assert main_layout(scenes) == "split"


def test_the_zoom_follows_the_subject_of_each_scenes_layout() -> None:
    clip = ClipSpan(1, 0.0, 4.0)
    plan = plan_crop(clip, "9:16", FRAME, faces_by_time(clip, {(0, 4): ONE}), [])
    shifted = plan.model_copy(
        update={"keyframes": [k.model_copy(update={"x": 0}) for k in plan.keyframes]}
    )
    parts = [ScenePart(0, 2, shifted, "fill"), ScenePart(2, 4, plan, "split")]
    zoom = [ZoomKeyframe(t=1.0, scale=1.5), ZoomKeyframe(t=3.0, scale=1.5)]

    assert framing_at(parts, plan, "fill", 0.5) == (shifted, "fill")
    assert framing_at(parts, plan, "fill", 2.0) == (plan, "split")
    assert framing_at(parts, plan, "fill", 9.0) == (plan, "split")
    assert framing_at([], plan, "pip", 1.0) == (plan, "pip")
    graph = zoom_filter(zoom, plan, "fill", 0.0, (1080, 1920), parts)
    # The face at x 640 is at 640/404 of the shifted window (clamped to its
    # right edge), and the split scene zooms about the center.
    assert "1080.0" in graph and "540.0" in graph
    assert graph != zoom_filter(zoom, plan, "fill", 0.0, (1080, 1920))


def near(color: Pixels, expected: tuple[int, int, int]) -> bool:
    """Return True if each channel of color is within 40 of expected."""
    return bool(np.all(np.abs(color.astype(int) - expected) <= 40))


@pytest.fixture(scope="module")
def stripes(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 6 s 1280x720 video with sound: red, green and blue thirds."""
    path = tmp_path_factory.mktemp("switch") / "stripes.mp4"
    video = (
        "color=size=1280x720:rate=30:duration=6,format=gbrp,"
        "geq=r='255*lt(X,427)':g='255*gte(X,427)*lt(X,853)':b='255*gte(X,853)',"
        "format=yuv420p"
    )
    run_ffmpeg(
        ["-f", "lavfi", "-i", video, "-f", "lavfi", "-i"]
        + ["anullsrc=r=48000:cl=stereo", "-t", "6", "-c:v", "libx264"]
        + ["-c:a", "aac", "-shortest", path]
    )
    return path


def test_a_clip_renders_its_scenes_in_their_layouts_one_after_another(
    stripes: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    clip = ClipSpan(1, 1.0, 5.0)
    # The smaller middle face is in the grid, not in the split.
    trio = [face(213), face(640, size=60), face(1067)]
    plan = plan_crop(clip, "9:16", FRAME, faces_by_time(clip, {(0, 6): trio}), [])
    layouts = ["grid", "split", "fit", "screenshare", "fill"]
    parts = [
        ScenePart(1.0 + 0.8 * n, 1.0 + 0.8 * (n + 1), plan, layout)
        for n, layout in enumerate(layouts)
    ]
    scenes = [SceneReframe(start=p.start, end=p.end, layout=p.layout) for p in parts]
    assert main_layout(scenes) == "grid"

    video = render_clip(
        stripes, tmp_path / "switch.mp4", 1.0, 5.0, plan, "grid",
        render_settings, scenes=parts,
    )  # fmt: skip

    info = probe_media(video)
    assert (info.width, info.height, info.fps) == (1080, 1920, 30)
    assert info.duration == pytest.approx(4.0, abs=0.2)
    grid, split, fit, share = (frame_at(video, 0.4 + 0.8 * n) for n in range(4))
    for n, color in enumerate((RED, GREEN, BLUE)):
        assert near(grid[320 + 640 * n, 540], color)
    assert near(split[480, 540], RED) and near(split[1440, 540], BLUE)
    for x, color in ((100, RED), (540, GREEN), (980, BLUE)):
        assert near(fit[960, x], color)
        assert near(share[480, x], color)
