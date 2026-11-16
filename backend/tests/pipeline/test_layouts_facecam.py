"""Tests of the screenshare and gameplay layouts (SPEC-v2 3.3,
pipeline/facecam): their cells and filter graphs, and clips rendered with
ffmpeg in them, of the fixture (size, codecs, duration) and of a "stream"
video whose facecam is a red square in the bottom right corner (what each
cell of the output shows)."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import Aspect, CropPlan, FaceBox, FrameBox, Layout
from clipforge.pipeline.facecam import facecam_cells
from clipforge.pipeline.layouts import layout_graph
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from frames import Pixels, frame_at

FRAME = (1280, 720)
CLIP = ClipSpan(1, 2.0, 4.0)
RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)
SAMPLES = 20
# The stream video's facecam: the red square x 960-1280, y 400-720.
CAM_BOX = FrameBox(x=0.75, y=400 / 720, width=0.25, height=320 / 720)


def face(center_x: float, center_y: float, size: float = 100.0) -> FaceBox:
    """Return a size px face centered at center_x, center_y."""
    half = size / 2
    return FaceBox(
        x=center_x - half, y=center_y - half, width=size, height=size, score=0.9
    )


def cam_faces(count: int = SAMPLES) -> list[list[FaceBox]]:
    """count samples with a face in the stream video's facecam."""
    return [[face(1120, 560)] for _ in range(count)]


def near(color: Pixels, expected: tuple[int, int, int]) -> bool:
    """Return True if each channel of color is within 40 of expected."""
    return bool(np.all(np.abs(color.astype(int) - expected) <= 40))


@pytest.fixture(scope="module")
def stream(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 6 s 1280x720 video with sound: green left half, blue right half,
    and a red 320x320 facecam in the bottom right corner."""
    path = tmp_path_factory.mktemp("stream") / "stream.mp4"
    cam = "gte(X,960)*gte(Y,400)"
    video = (
        "color=size=1280x720:rate=30:duration=6,format=gbrp,"
        f"geq=r='255*{cam}':g='255*lt(X,640)*not({cam})':"
        f"b='255*gte(X,640)*not({cam})',format=yuv420p"
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


def test_facecam_cells_split_the_long_side() -> None:
    assert facecam_cells("screenshare", (1080, 1920)) == ((1080, 960), (1080, 960))
    assert facecam_cells("gameplay", (1080, 1920)) == ((1080, 1280), (1080, 640))
    assert facecam_cells("gameplay", (1080, 1350)) == ((1080, 900), (1080, 450))
    assert facecam_cells("gameplay", (1080, 1080)) == ((720, 1080), (360, 1080))
    assert facecam_cells("screenshare", (1920, 1080)) == ((960, 1080), (960, 1080))


def test_the_screenshare_graph_fits_the_video_over_the_facecam() -> None:
    plan = plan_crop(CLIP, "9:16", FRAME, cam_faces(), [])
    assert plan.facecam is not None

    graph = layout_graph(plan, "screenshare", CLIP.start, (1080, 1920), 30)
    black = layout_graph(
        plan.model_copy(update={"background": "black"}),
        "screenshare",
        CLIP.start,
        (1080, 1920),
        30,
    )
    wide = layout_graph(plan, "screenshare", CLIP.start, (1920, 1080), 30, tag="1")

    assert graph.startswith("[0:V:0]fps=30,split=2[video][cam];[video]null,split=2")
    assert "boxblur" in graph and "scale=1080:960:force_original_aspect" in graph
    box = plan.facecam
    assert (
        f"[cam]crop=w=iw*{box.width:.4f}:h=ih*{box.height:.4f}:"
        f"x=iw*{box.x:.4f}:y=ih*{box.y:.4f},"
        "scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,"
        "setsar=1[cammed]"
    ) in graph
    assert graph.endswith("[framed][cammed]vstack=inputs=2,setsar=1[v]")
    assert "pad=1080:960:(ow-iw)/2:(oh-ih)/2:black" in black
    assert wide.endswith("[framed1][cammed1]hstack=inputs=2,setsar=1[v]")


def test_the_gameplay_graph_puts_the_facecam_above_the_cropped_video() -> None:
    plan = plan_crop(CLIP, "9:16", FRAME, cam_faces(), [])

    graph = layout_graph(plan, "gameplay", CLIP.start, (1080, 1920), 30)

    assert (
        "[video]null,scale=1080:1280:force_original_aspect_ratio=increase,"
        "crop=1080:1280,setsar=1[framed]"
    ) in graph
    assert "crop=1080:640,setsar=1[cammed]" in graph
    assert graph.endswith("[cammed][framed]vstack=inputs=2,setsar=1[v]")


def test_without_a_facecam_the_video_takes_the_whole_output() -> None:
    plan = plan_crop(CLIP, "9:16", FRAME, [[] for _ in range(SAMPLES)], [])
    assert plan.facecam is None

    screen = layout_graph(plan, "screenshare", CLIP.start, (1080, 1920), 30)
    game = layout_graph(plan, "gameplay", CLIP.start, (1080, 1920), 30)

    assert screen == layout_graph(plan, "fit", CLIP.start, (1080, 1920), 30)
    assert game == (
        "[0:V:0]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1[v]"
    )


@pytest.mark.parametrize(
    ("layout", "aspect", "size"),
    [
        ("screenshare", "9:16", (1080, 1920)),
        ("screenshare", "16:9", (1920, 1080)),
        ("gameplay", "9:16", (1080, 1920)),
        ("gameplay", "1:1", (1080, 1080)),
        ("gameplay", "4:5", (1080, 1350)),
    ],
)
def test_each_facecam_layout_renders_the_fixture(
    sample_mp4: Path,
    tmp_path: Path,
    render_settings: RenderSettings,
    layout: Layout,
    aspect: Aspect,
    size: tuple[int, int],
) -> None:
    clip = ClipSpan(1, 10.0, 14.0)
    faces = [[face(1000, 500, 120)] for _ in range(40)]
    plan = plan_crop(clip, aspect, FRAME, faces, [])
    assert plan.facecam is not None

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


def test_screenshare_shows_the_whole_screen_above_the_found_facecam(
    stream: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    plan = plan_crop(CLIP, "9:16", FRAME, cam_faces(), [])

    frame = frame_at(
        render(stream, tmp_path / "s.mp4", plan, "screenshare", render_settings),
        1.0,
    )

    # The 1280x720 screen fits the 1080x960 top cell as 1080x608 at y 176.
    assert near(frame[480, 100], GREEN) and near(frame[400, 700], BLUE)
    assert near(frame[176 + 540, 1000], RED)
    # The found facecam (300 px around the face) fills the bottom cell.
    for y, x in ((1000, 60), (1440, 540), (1880, 1020)):
        assert near(frame[y, x], RED)


def test_gameplay_shows_the_drawn_facecam_above_the_middle_of_the_game(
    stream: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    faceless = plan_crop(CLIP, "9:16", FRAME, [[] for _ in range(SAMPLES)], [])
    plan = faceless.model_copy(update={"facecam": CAM_BOX})

    frame = frame_at(
        render(stream, tmp_path / "g.mp4", plan, "gameplay", render_settings),
        1.0,
    )

    for y, x in ((20, 20), (320, 540), (620, 1060)):
        assert near(frame[y, x], RED)
    # The game covers 1080x1280: source x 336-944, green then blue.
    assert near(frame[1300, 100], GREEN) and near(frame[1900, 1000], BLUE)
