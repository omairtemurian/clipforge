"""Tests of the grid and pip layouts (SPEC-v2 3.3, pipeline/layouts): their
filter graphs, and clips rendered with ffmpeg in them, of the fixture
(size, codecs, duration) and of a video of three colored stripes (what
each part of the output shows)."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import Aspect, CropPlan, FaceBox, Layout
from clipforge.pipeline.layouts import (
    grid_cells,
    inset_geometry,
    layout_graph,
)
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from frames import Pixels, frame_at

FRAME = (1280, 720)
CLIP = ClipSpan(1, 2.0, 4.0)
RED, GREEN, BLUE, WHITE = (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)
SAMPLES = 20


def face(center_x: float, size: float = 100.0) -> FaceBox:
    """Return a size px face centered at center_x, 360."""
    half = size / 2
    return FaceBox(x=center_x - half, y=360 - half, width=size, height=size, score=0.9)


def three_faces() -> list[list[FaceBox]]:
    """The samples of CLIP with a face on each stripe."""
    return [[face(213), face(640), face(1067)] for _ in range(SAMPLES)]


def near(color: Pixels, expected: tuple[int, int, int]) -> bool:
    """Return True if each channel of color is within 40 of expected."""
    return bool(np.all(np.abs(color.astype(int) - expected) <= 40))


@pytest.fixture(scope="module")
def stripes(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 6 s 1280x720 video with sound: red, green and blue thirds."""
    path = tmp_path_factory.mktemp("stripes") / "stripes.mp4"
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


def render(
    source: Path,
    out: Path,
    plan: CropPlan,
    layout: Layout,
    settings: RenderSettings,
    clip: ClipSpan = CLIP,
) -> Path:
    """Render clip of source framed in layout with plan into out."""
    return render_clip(source, out, clip.start, clip.end, plan, layout, settings)


def test_grid_cells_are_rows_in_portrait_and_columns_otherwise() -> None:
    assert grid_cells((1080, 1920)) == [(1080, 640)] * 3
    assert grid_cells((1080, 1350)) == [(1080, 450)] * 3
    assert grid_cells((1080, 1080)) == [(360, 1080)] * 3
    assert grid_cells((1920, 1080)) == [(640, 1080)] * 3
    # Thirds are even; the last cell takes what is left.
    assert grid_cells((1080, 1600)) == [(1080, 532), (1080, 532), (1080, 536)]


def test_inset_geometry_is_a_share_of_the_shorter_side() -> None:
    assert inset_geometry((1080, 1920)) == (388, 6, 42)
    assert inset_geometry((1920, 1080)) == (388, 6, 42)
    assert inset_geometry((540, 960)) == (194, 2, 22)


def test_the_grid_graph_crops_each_window_and_stacks_the_cells() -> None:
    plan = plan_crop(CLIP, "9:16", FRAME, three_faces(), [])
    left, middle, right = plan.grid

    graph = layout_graph(plan, "grid", CLIP.start, (1080, 1920), 30)
    wide = layout_graph(plan, "grid", CLIP.start, (1920, 1080), 30, tag="1")

    assert graph.startswith("[0:V:0]fps=30,split=3[cell0][cell1][cell2];")
    for n, window in enumerate((left, middle, right)):
        assert f"[cell{n}]crop=w={window.width}:h={window.height}:" in graph
        assert f"scale=1080:640,setsar=1[celled{n}]" in graph
    assert graph.endswith("[celled0][celled1][celled2]vstack=inputs=3,setsar=1[v]")
    assert "[celled01][celled11][celled21]hstack=inputs=3" in wide
    assert "scale=640:1080" in wide


def test_the_grid_graph_needs_the_plans_grid_windows() -> None:
    plan = plan_crop(CLIP, "9:16", FRAME, three_faces(), [])

    with pytest.raises(ValueError, match="grid windows"):
        layout_graph(plan.model_copy(update={"grid": []}), "grid", 2.0, FRAME, 30)


def test_the_pip_graph_overlays_a_bordered_inset_top_right() -> None:
    faces = [[face(213, 200), face(1067)] for _ in range(SAMPLES)]
    plan = plan_crop(CLIP, "9:16", FRAME, faces, [])
    assert plan.inset is not None

    graph = layout_graph(plan, "pip", CLIP.start, (1080, 1920), 30)
    whole = layout_graph(
        plan.model_copy(update={"inset": None}), "pip", CLIP.start, (1080, 1920), 30
    )

    side = plan.inset.width
    assert f"[pipsmall]crop=w={side}:h={side}:" in graph
    assert "scale=388:388,setsar=1,pad=w=iw+12:h=ih+12:x=6:y=6:color=white" in graph
    assert graph.endswith("[pipbase][pipcorner]overlay=x=W-w-42:y=42,setsar=1[v]")
    assert (
        "[pipsmall]scale=388:388:force_original_aspect_ratio=decrease:"
        "force_divisible_by=2,setsar=1,pad=" in whole
    )


@pytest.mark.parametrize(
    ("layout", "aspect", "size"),
    [
        ("grid", "9:16", (1080, 1920)),
        ("grid", "16:9", (1920, 1080)),
        ("pip", "9:16", (1080, 1920)),
        ("pip", "1:1", (1080, 1080)),
    ],
)
def test_each_layout_renders_the_fixture(
    sample_mp4: Path,
    tmp_path: Path,
    render_settings: RenderSettings,
    layout: Layout,
    aspect: Aspect,
    size: tuple[int, int],
) -> None:
    clip = ClipSpan(1, 10.0, 14.0)
    faces = [[face(213), face(640, 120), face(1067)] for _ in range(40)]
    plan = plan_crop(clip, aspect, FRAME, faces, [])

    video = render(
        sample_mp4, tmp_path / "out.mp4", plan, layout, render_settings, clip
    )

    info = probe_media(video)
    assert (info.width, info.height, info.fps) == (*size, 30)
    assert (info.video_codec, info.pix_fmt, info.audio_codec) == (
        "h264",
        "yuv420p",
        "aac",
    )
    assert info.duration == pytest.approx(4.0, abs=0.2)


def test_grid_shows_the_left_middle_and_right_speaker(
    stripes: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    tall = plan_crop(CLIP, "9:16", FRAME, three_faces(), [])
    wide = plan_crop(CLIP, "16:9", FRAME, three_faces(), [])

    rows = frame_at(
        render(stripes, tmp_path / "rows.mp4", tall, "grid", render_settings), 1.0
    )
    columns = frame_at(
        render(stripes, tmp_path / "cols.mp4", wide, "grid", render_settings), 1.0
    )

    assert [w.xs[0] for w in tall.grid] == [0, 426, 854]
    for n, color in enumerate((RED, GREEN, BLUE)):
        assert near(rows[320 + 640 * n, 540], color)
        assert near(columns[540, 320 + 640 * n], color)


def test_pip_shows_the_subject_with_the_other_speaker_inset(
    stripes: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    faces = [[face(213, 200), face(1067)] for _ in range(SAMPLES)]
    plan = plan_crop(CLIP, "9:16", FRAME, faces, [])
    assert plan.inset is not None and plan.inset.width == 300

    frame = frame_at(
        render(stripes, tmp_path / "pip.mp4", plan, "pip", render_settings), 1.0
    )

    # The inset's 400 px bordered square is 42 px from the top and right.
    assert near(frame[1000, 200], RED) and near(frame[1000, 600], RED)
    assert near(frame[242, 838], BLUE)
    assert near(frame[242, 640], WHITE) and near(frame[44, 838], WHITE)
    assert near(frame[600, 838], RED)


def test_pip_without_another_face_insets_the_whole_frame(
    stripes: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    faces = [[face(640, 200)] for _ in range(SAMPLES)]
    plan = plan_crop(CLIP, "9:16", FRAME, faces, [])
    assert plan.inset is None

    frame = frame_at(
        render(stripes, tmp_path / "pip.mp4", plan, "pip", render_settings), 1.0
    )

    # The 1280x720 frame fits the inset as 388x218, bordered to 400x230.
    assert near(frame[1000, 540], GREEN)
    assert near(frame[157, 644 + 60], RED)
    assert near(frame[157, 644 + 194], GREEN)
    assert near(frame[157, 644 + 330], BLUE)
    assert near(frame[157, 640], WHITE)
