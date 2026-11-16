"""Tests of the Pro Edit renderer core with ffmpeg (SPEC-v3 3.6, TASK-207).

The source is a still (one testsrc2 frame for 6 s, so nothing moves but
what the renderer draws) with a tone; the clip is 1-5 s of it, framed 9:16
with no faces. Each grade item draws on exactly the frames of its window
(frame k starts at k / 30 s of the clip), measured with
proedit/features/color: black and white has no saturation, dark lowers the
luma, desat keeps part of the color, the vignette darkens the corners and
the grain changes from frame to frame. Renders use libx264 (deterministic;
the cut test runs with each encoder ffmpeg has) and ffprobe checks the
files.
"""

import shutil
from pathlib import Path

import numpy as np
import pytest
from builders import make_clip, said
from clipforge.config import RenderSettings
from clipforge.ffmpeg import ffprobe_json, run_ffmpeg
from clipforge.models import CaptionCensor, CaptionStyle, EdlItem, FaceBox
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import crop_path, plan_crop
from clipforge.pipeline.step import SOURCE, TRANSCRIPT, write_json
from clipforge.proedit.edl import EdlValidationError
from clipforge.proedit.features.color import BW_SATURATION, frame_color
from clipforge.proedit.render.base import clip_base
from clipforge.proedit.render.run import UndrawnItemsError, render_plan
from edl_fakes import item, plan
from frames import Pixels, frame_hashes, numbered_frames
from proedit_render import CLIP, base_of

X264 = RenderSettings(encoder="libx264")
# Clip seconds -> frames at 30 fps: bw 15-29, dark 36-47, desat 54-65,
# vignette 72-83, grain 90-107.
LOOKS = [
    item(1, "grade_change", 0.5, 1.0, params={"look": "bw"}),
    item(2, "grade_change", 1.2, 1.6, params={"look": "dark"}),
    item(3, "grade_change", 1.8, 2.2, params={"look": "desat"}),
    item(4, "vignette", 2.4, 2.8, params={"strength": 0.4}),
    item(5, "grain", 3.0, 3.6, params={"strength": 0.2, "seed": 7}),
]


@pytest.fixture(scope="module")
def still(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 6 s 1280x720 30 fps h264/aac video of one testsrc2 frame and a tone."""
    directory = tmp_path_factory.mktemp("proedit_render")
    png, video = directory / "still.png", directory / "still.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=1280x720", "-frames:v", "1", png])
    run_ffmpeg(
        ["-loop", "1", "-framerate", "30", "-i", png]
        + ["-f", "lavfi", "-i", "sine=frequency=440", "-t", "6"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video]
    )
    return video


def render(source: Path, output: Path, items: list[EdlItem]) -> Path:
    """Render the proxy of CLIP of source with items, with libx264."""
    return render_plan(
        base_of(source), plan(items, "pro"), output, quality="proxy", settings=X264
    )


@pytest.fixture(scope="module")
def graded(
    still: Path, tmp_path_factory: pytest.TempPathFactory, module_data_dir: Path
) -> Path:
    """The proxy of CLIP with the LOOKS items (protected looks cache their
    LUTs in module_data_dir)."""
    return render(still, tmp_path_factory.mktemp("graded") / "graded.mp4", LOOKS)


def corners(frame: Pixels) -> float:
    """Return the mean of the 4 corner tenths of frame (0..255)."""
    height, width, _ = frame.shape
    h, w = height // 10, width // 10
    parts = [frame[:h, :w], frame[:h, -w:], frame[-h:, :w], frame[-h:, -w:]]
    return float(np.mean([part.mean() for part in parts]))


def middle(frame: Pixels) -> float:
    """Return the mean of the middle tenth of frame (0..255)."""
    height, width, _ = frame.shape
    rows = slice(height * 9 // 20, height * 11 // 20)
    cols = slice(width * 9 // 20, width * 11 // 20)
    return float(frame[rows, cols].mean())


def change(a: Pixels, b: Pixels) -> float:
    """Return the mean absolute difference of two frames."""
    return float(np.abs(a.astype(np.int16) - b).mean())


def stream_info(video: Path) -> tuple[dict[str, object], dict[str, object], float]:
    """Return video's video stream, audio stream and duration (ffprobe)."""
    probe = ffprobe_json(video)
    streams = probe["streams"]
    picture = next(s for s in streams if s["codec_type"] == "video")
    sound = next(s for s in streams if s["codec_type"] == "audio")
    return picture, sound, float(probe["format"]["duration"])


def test_black_and_white_covers_exactly_its_window(graded: Path) -> None:
    frames = numbered_frames(graded, [0, 14, 15, 29, 30])
    saturation = {k: frame_color(f).saturation for k, f in frames.items()}
    assert saturation[15] < BW_SATURATION and saturation[29] < BW_SATURATION
    for outside in (0, 14, 30):
        assert saturation[outside] > 0.5


def test_dark_desat_vignette_and_grain_show_on_their_frames(graded: Path) -> None:
    f = numbered_frames(graded, [33, 40, 50, 60, 69, 78, 86, 87, 95, 96, 112])
    plain = frame_color(f[33])
    assert frame_color(f[40]).luma < 0.85 * plain.luma
    assert frame_color(f[50]).luma == pytest.approx(plain.luma, abs=0.01)
    desat = frame_color(f[60]).saturation
    assert 0.25 * plain.saturation < desat < 0.6 * plain.saturation
    assert corners(f[78]) < 0.7 * corners(f[69])
    assert middle(f[78]) == pytest.approx(middle(f[69]), rel=0.03)
    assert change(f[86], f[87]) < 0.5
    assert change(f[95], f[96]) > 1.5
    assert change(f[95], f[86]) > 1.5
    assert change(f[112], f[86]) < 0.5


def test_the_proxy_is_540p_h264_with_aac_of_the_clip_length(graded: Path) -> None:
    picture, sound, duration = stream_info(graded)
    assert (picture["codec_name"], picture["pix_fmt"]) == ("h264", "yuv420p")
    assert (picture["width"], picture["height"]) == (540, 960)
    assert sound["codec_name"] == "aac"
    assert duration == pytest.approx(4.0, abs=0.2)


def test_the_same_plan_renders_the_same_frames(
    graded: Path, still: Path, tmp_path: Path
) -> None:
    again = render(still, tmp_path / "again.mp4", LOOKS)
    hashes = frame_hashes(graded)
    assert len(hashes) == 120
    assert frame_hashes(again) == hashes


def test_the_final_is_cut_and_drawn_in_clip_time(
    still: Path, tmp_path: Path, render_settings: RenderSettings
) -> None:
    # 2-3 s of the source is cut: the clip plays 1-2 s and 3-5 s of it,
    # and its 2.0-2.5 s (frames 60-74) is 4.0-4.5 s of the source.
    bw = [item(1, "grade_change", 2.0, 2.5, params={"look": "bw"})]
    progress: list[float] = []
    output = render_plan(
        base_of(still, [(2.0, 3.0)]),
        plan(bw, "pro"),
        tmp_path / "final.mp4",
        settings=render_settings,
        on_progress=progress.append,
    )
    picture, sound, duration = stream_info(output)
    assert (picture["codec_name"], picture["width"], picture["height"]) == (
        "h264",
        1080,
        1920,
    )
    assert sound["codec_name"] == "aac"
    assert duration == pytest.approx(3.0, abs=0.2)
    frames = numbered_frames(output, [59, 60, 74, 75])
    saturation = {k: frame_color(f).saturation for k, f in frames.items()}
    assert saturation[60] < BW_SATURATION and saturation[74] < BW_SATURATION
    assert saturation[59] > 0.5 and saturation[75] > 0.5
    assert progress and max(progress) <= 1.0
    assert not (tmp_path / "final.tmp.mp4").exists()


def test_a_plan_with_an_undrawn_item_is_refused(still: Path, tmp_path: Path) -> None:
    output = tmp_path / "refused.mp4"
    text = [item(1, "text_pop", 1.0, 1.5)]
    with pytest.raises(UndrawnItemsError, match="does not draw text_pop"):
        render(still, output, text)
    with pytest.raises(EdlValidationError):
        render(still, output, [item(1, "grain", 3.5, 4.5)])
    assert list(tmp_path.iterdir()) == []


def test_the_base_of_a_clip_keeps_its_cuts_and_censor(
    still: Path, tmp_path: Path
) -> None:
    # "shit" at 3.5-3.8 s of the source is 1.5-1.8 s of the cut clip.
    shutil.copy(still, tmp_path / SOURCE)
    write_json(tmp_path / TRANSCRIPT, said(("so", 1.2, 1.4), ("shit", 3.5, 3.8)))
    faces: list[list[FaceBox]] = [[] for _ in sample_times(CLIP.start, CLIP.end)]
    write_json(
        crop_path(tmp_path, CLIP.clip_id),
        plan_crop(CLIP, "9:16", (1280, 720), faces, []),
    )
    style = CaptionStyle(censor=CaptionCensor(mode="beep"))
    clip = make_clip(
        "minimal",
        start=CLIP.start,
        end=CLIP.end,
        cut_ranges=[(2.0, 3.0)],
        caption_style=style,
    )
    base = clip_base(tmp_path, clip, 30)
    assert (base.source, base.start, base.end) == (tmp_path / SOURCE, 1.0, 5.0)
    assert base.plan.aspect == "9:16" and base.layout == clip.layout
    assert "between(t,1.4" in base.censor
    assert [pytest.approx(span) for span in base.speech] == [(0.2, 0.4), (1.5, 1.8)]
    assert base.sounds == {}
    assert base.duration(30) == pytest.approx(3.0)
    output = render_plan(
        base, plan([], "pro"), tmp_path / "base.mp4", quality="proxy", settings=X264
    )
    assert stream_info(output)[2] == pytest.approx(3.0, abs=0.2)
