"""Auto zoom-out moments on real face detection (TASK-198): the fixture's
single framed speaker stays in fill, a wide two-shot zooms out."""

from collections.abc import Callable
from pathlib import Path

import pytest
from clipforge.config import Settings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import CropPlan, SceneReframe, SignalList, SourceMeta
from clipforge.pipeline.layout_auto import zoom_out_scenes
from clipforge.pipeline.reframe import ClipSpan
from clipforge.pipeline.reframe_run import reframe_clips
from clipforge.pipeline.step import META, SIGNALS, SOURCE, write_json
from clipforge.pipeline.zoom_out_rules import zoom_params
from clipforge.zoom_out_settings import ZoomOutSettings

CopyJob = Callable[..., Path]
FRAME = (1280, 720)
PARAMS = zoom_params("balanced", ZoomOutSettings())


def zoom_outs(job: Path, clip: ClipSpan, cfg: Settings) -> tuple[CropPlan, list]:
    """Reframe clip of job for 9:16 and return its plan and its zoom-out
    scenes (start, end, layout) as the auto layout plans them."""
    (path,) = reframe_clips(job, [clip], "9:16", cfg=cfg)
    plan = CropPlan.model_validate_json(path.read_text(encoding="utf-8"))
    whole = [SceneReframe(start=clip.start, end=clip.end, layout=plan.layout)]
    assert PARAMS is not None
    scenes = zoom_out_scenes(plan, whole, FRAME, [], [], PARAMS)
    return plan, [(s.start, s.end, s.layout) for s in scenes if s.layout != "fill"]


@pytest.fixture(scope="session")
def wide_pair(sample_mp4: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A job whose 12 s source is 5-13 s of the fixture (one framed face),
    then 4 s of two half-size copies of it side by side (two faces about
    640 px apart, a wide two-shot)."""
    job = tmp_path_factory.mktemp("wide_pair")
    graph = (
        "[0:v]trim=5:13,setpts=PTS-STARTPTS[one];"
        "[0:v]trim=20:24,setpts=PTS-STARTPTS,scale=640:360,split[a][b];"
        "[a][b]hstack,pad=1280:720:0:180[two];"
        "[one][two]concat=n=2[v]"
    )
    run_ffmpeg(
        ["-i", sample_mp4, "-filter_complex", graph, "-map", "[v]"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", job / SOURCE]
    )
    meta = SourceMeta(
        title="wide pair",
        duration=12.0,
        width=1280,
        height=720,
        fps=30.0,
        timeframe_start=0.0,
        timeframe_end=12.0,
    )
    write_json(job / META, meta)
    write_json(job / SIGNALS, SignalList([]))
    return job


@pytest.mark.slow
def test_the_fixtures_framed_speaker_never_zooms_out(
    copy_job: CopyJob, face_cfg: Settings
) -> None:
    job = copy_job()
    write_json(job / SIGNALS, SignalList([]))

    plan, found = zoom_outs(job, ClipSpan(1, 0.5, 20.5), face_cfg)

    assert plan.layout == "fill"
    assert found == []


@pytest.mark.slow
def test_a_wide_two_shot_zooms_out(wide_pair: Path, face_cfg: Settings) -> None:
    plan, found = zoom_outs(wide_pair, ClipSpan(1, 0.0, 12.0), face_cfg)

    assert plan.layout == "fill"
    assert len(found) == 1
    ((start, end, layout),) = found
    # The detector misses one of the small faces now and then at first.
    assert 8.0 <= start <= 9.0 and end == 12.0
    assert layout in ("fit", "square_blur")
