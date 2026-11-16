"""Regression tests for rendering a long clip (steering: a 20 min clip in
"Captions only" mode failed with `[Errno 7] Argument list too long`): its
crop expressions, one term per reframe keyframe, are read by ffmpeg from a
file, and a clip framed scene by scene carries only each scene's keyframes
(layout_parts.plan_span)."""

import subprocess
from pathlib import Path
from typing import Any

import pytest
from clipforge import ffmpeg
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import CropKeyframe, CropPlan, CropWindow, FaceBox
from clipforge.pipeline.layout_parts import plan_span, square_centers
from clipforge.pipeline.layouts import layout_graph
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.scene_graph import ScenePart, scene_graph

# A 20 min clip with more than 5,000 crop keyframes (5 a second would be
# 6,000), of a tiny 1 frame a second source so that it renders in seconds.
LENGTH = 1200.0
KEYFRAMES = 6000
FRAME = (128, 72)
SIZE = (36, 64)


@pytest.fixture(scope="module")
def long_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 20 min 128x72 video at 1 frame a second, with silent sound."""
    path = tmp_path_factory.mktemp("long") / "long.mp4"
    run_ffmpeg(
        ["-f", "lavfi", "-i", f"testsrc2=size=128x72:rate=1:duration={LENGTH}"]
        + ["-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", str(LENGTH)]
        + ["-c:v", "libx264", "-preset", "ultrafast", "-g", "600"]
        + ["-c:a", "aac", "-b:a", "16k", "-shortest", path]
    )
    return path


def moving_plan(count: int = KEYFRAMES, length: float = LENGTH) -> CropPlan:
    """A 9:16 plan of a FRAME source whose 40x72 window moves at each of
    count keyframes over length seconds."""
    times = [length * k / count for k in range(count)]
    xs = [(k * 7) % (FRAME[0] - 40) for k in range(count)]
    face = FaceBox(x=10, y=10, width=20, height=20, score=0.9)
    split = CropWindow(width=40, height=36, y=0, xs=xs)
    return CropPlan(
        clip_id=1,
        start=0.0,
        end=length,
        aspect="9:16",
        width=40,
        height=72,
        y=0,
        keyframes=[
            CropKeyframe(t=t, x=x, faces=[face] * (k % 3))
            for k, (t, x) in enumerate(zip(times, xs, strict=True))
        ],
        layout="fill",
        split=(split, split),
    )


def test_a_20_min_clip_with_6000_keyframes_renders_with_a_short_command(
    long_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = moving_plan()
    assert len(layout_graph(plan, "fill", 0.0, SIZE, 2)) > 100_000
    commands: list[list[str]] = []
    real_run = subprocess.run

    def recording_run(command: list[str], **kwargs: Any) -> Any:
        commands.append(command)
        return real_run(command, **kwargs)

    monkeypatch.setattr(ffmpeg.subprocess, "run", recording_run)
    output = tmp_path / "long_clip.mp4"
    settings = RenderSettings(fps=2, preset="ultrafast", audio_bitrate="16k")

    render_clip(long_source, output, 0.0, LENGTH, plan, "fill", settings, size=SIZE)

    assert any("-/filter_complex" in command for command in commands)
    assert all(sum(len(arg) for arg in command) < 100_000 for command in commands)
    info = probe_media(output)
    assert (info.width, info.height) == SIZE
    assert info.duration == pytest.approx(LENGTH, abs=1.0)


def test_plan_span_keeps_the_keyframes_around_the_span() -> None:
    plan = moving_plan(100, 100.0)

    part = plan_span(plan, 40.5, 50.0)

    # The last keyframe at or before 40.5 s is at 40 s, the first at or after
    # 50 s at 50 s; 5 more on each side keep the square's smoothing.
    assert [k.t for k in part.keyframes] == [float(t) for t in range(35, 56)]
    assert part.split[0].xs == plan.split[0].xs[35:56]
    full, trimmed = square_centers(plan), square_centers(part)
    assert trimmed[5:16] == full[40:51]
    assert plan_span(plan, 0.0, 100.0) is plan


def test_scene_parts_of_a_long_clip_carry_only_their_own_keyframes() -> None:
    plan = moving_plan(2000, 400.0)
    parts = [
        ScenePart(start, start + 10.0, plan, "fill" if index % 2 else "square_blur")
        for index, start in enumerate(range(0, 400, 10))
    ]

    graph = scene_graph(parts, 0.0, SIZE, 30)

    # 40 parts of 50 keyframes each instead of 40 copies of all 2,000.
    assert len(graph) < len(layout_graph(plan, "fill", 0.0, SIZE, 30)) * 2
