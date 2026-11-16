"""Tests of reframe (SPEC 6.8) on videos: the faces that MediaPipe finds and
the crop plans of clips.

The fixture's drawn face moves from x 200 to 1080 at a constant speed over
its 60 s (expected.json); the slow tests run the downloaded face model.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import mediapipe
import numpy as np
import pytest
from clipforge.config import Settings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.model_files import FACE_MODELS, face_model_path
from clipforge.models import CropPlan, FaceBox, SignalEvent, SignalList, SourceMeta
from clipforge.pipeline.faces import Frame, analysis_size, find_faces
from clipforge.pipeline.reframe import ClipSpan, crop_path
from clipforge.pipeline.reframe_run import reframe_clips
from clipforge.pipeline.step import META, SIGNALS, SOURCE, StepError, write_json

MakeMedia = Callable[..., Path]
CopyJob = Callable[..., Path]
# The 9:16 window in a 1280x720 frame.
CROP_WIDTH = 404
# Where far_face puts the shrunk fixture.
FAR_X = 800


def face_center(expected: dict[str, Any], t: float) -> float:
    """Return the x of the fixture face's center at t seconds."""
    face = expected["face"]
    start, end = face["start"], face["end"]
    speed = (end["center_x"] - start["center_x"]) / (end["t"] - start["t"])
    return float(start["center_x"] + speed * (t - start["t"]))


@pytest.fixture(scope="session")
def two_shots(sample_mp4: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A job whose 4 s source has two shots of the fixture: 5-7 s, with the
    face near x 273-303, then 50-52 s, with it near 933-963, and a scene cut
    at 2 s in signals.json."""
    job = tmp_path_factory.mktemp("two_shots")
    trims = "".join(
        f"[0:v]trim={start}:{start + 2},setpts=PTS-STARTPTS[v{k}];"
        for k, start in enumerate((5, 50))
    )
    run_ffmpeg(
        ["-i", sample_mp4, "-filter_complex", f"{trims}[v0][v1]concat=n=2[v]"]
        + ["-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", job / SOURCE]
    )
    meta = SourceMeta(
        title="two shots",
        duration=4.0,
        width=1280,
        height=720,
        fps=30.0,
        timeframe_start=0.0,
        timeframe_end=4.0,
    )
    write_json(job / META, meta)
    cut = SignalEvent(kind="scene_cut", start=2.0, end=2.0, intensity=1.0)
    write_json(job / SIGNALS, SignalList([cut]))
    return job


@pytest.fixture(scope="session")
def far_face(sample_mp4: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A job whose 4 s 1280x720 source is 5-9 s of the fixture shrunk to
    400x225 at (800, 100): a far face about 75 px wide, near x 885-903."""
    job = tmp_path_factory.mktemp("far_face")
    run_ffmpeg(
        ["-ss", "5", "-t", "4", "-i", sample_mp4, "-an"]
        + ["-vf", f"scale=400:225,pad=1280:720:{FAR_X}:100"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", job / SOURCE]
    )
    meta = SourceMeta(
        title="far face",
        duration=4.0,
        width=1280,
        height=720,
        fps=30.0,
        timeframe_start=0.0,
        timeframe_end=4.0,
    )
    write_json(job / META, meta)
    write_json(job / SIGNALS, SignalList([]))
    return job


@pytest.mark.slow
def test_reframe_follows_the_face_of_the_fixture(
    copy_job: CopyJob,
    face_cfg: Settings,
    expected: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    job = copy_job()
    write_json(job / SIGNALS, SignalList([]))
    progress: list[float] = []

    paths = reframe_clips(
        job,
        [ClipSpan(4, 0.5, 34.35)],
        "9:16",
        cfg=face_cfg,
        on_progress=progress.append,
    )

    assert paths == [job / "crop_4.json"]
    plan = CropPlan.model_validate_json(paths[0].read_text(encoding="utf-8"))
    assert (plan.clip_id, plan.start, plan.end, plan.aspect) == (4, 0.5, 34.35, "9:16")
    assert (plan.width, plan.height, plan.y, len(plan.keyframes)) == (404, 720, 0, 339)
    # One face: fill. The split windows are 9:8 (half of 9:16) in 640 px.
    assert plan.layout == "fill"
    assert [(w.width, w.height, len(w.xs)) for w in plan.split] == [(640, 568, 339)] * 2
    for keyframe in plan.keyframes:
        center = face_center(expected, keyframe.t)
        (found,) = keyframe.faces
        assert found.x + found.width / 2 == pytest.approx(center, abs=25)
        assert found.score >= 0.5
        # The whole 240 px wide face is in the window.
        assert keyframe.x <= center - 120 and center + 120 <= keyframe.x + 404
    # Progress every 50 of the 339 samples, then done.
    assert progress[0] == 0.0 and progress[-1] == 1.0
    assert progress[1:7] == pytest.approx([k * 50 / 339 for k in range(1, 7)])
    assert progress == sorted(progress)
    assert all(keyframe.faces[0].subject for keyframe in plan.keyframes)
    message = "faces in 339 of 339 frames, objects in 0, crop 404x720"
    (logged,) = [m for m in caplog.messages if m.startswith("reframed clip 4 ")]
    assert logged.startswith("reframed clip 4 (0.5-34.4s) in ")
    assert " s per minute of video): " in logged
    assert logged.endswith(f"{message}, layout fill, subject in 339")


@pytest.mark.slow
def test_the_window_jumps_to_the_subject_at_a_scene_cut(
    two_shots: Path, face_cfg: Settings
) -> None:
    clip = ClipSpan(1, 0.0, 4.0)

    (path,) = reframe_clips(two_shots, [clip], "9:16", cfg=face_cfg)

    xs = [k.x for k in CropPlan.model_validate_json(path.read_bytes()).keyframes]
    assert len(xs) == 40
    # The face moves less than the 51.2 px half dead-zone in each shot, so
    # the window holds still; at the cut (sample 20, 2.0 s) it jumps.
    assert len(set(xs[:20])) == 1 and len(set(xs[20:])) == 1
    assert xs[0] == pytest.approx(273 - CROP_WIDTH / 2, abs=30)
    assert xs[20] == pytest.approx(933 - CROP_WIDTH / 2, abs=30)


@pytest.mark.slow
def test_without_the_scene_cut_the_window_pans_to_the_new_subject(
    two_shots: Path, face_cfg: Settings, tmp_path: Path
) -> None:
    for name in (SOURCE, META):
        (tmp_path / name).write_bytes((two_shots / name).read_bytes())
    write_json(tmp_path / SIGNALS, SignalList([]))

    (path,) = reframe_clips(tmp_path, [ClipSpan(1, 0.0, 4.0)], "9:16", cfg=face_cfg)

    xs = [k.x for k in CropPlan.model_validate_json(path.read_bytes()).keyframes]
    steps = [after - before for before, after in zip(xs, xs[1:], strict=False)]
    # The pan is at most 25% of the frame width a second (32 px a sample at
    # 10 samples a second), never back, and has no lag: it starts before the
    # new subject appears at sample 20 and is on its way to it at the end.
    assert max(steps) <= 0.25 * 1280 / 10 and min(steps) >= 0
    assert xs[0] == pytest.approx(273 - CROP_WIDTH / 2, abs=30)
    assert xs[0] < xs[19] < xs[20] < xs[39] < 933 - CROP_WIDTH / 2


@pytest.mark.slow
def test_reframe_finds_and_follows_a_small_far_face(
    far_face: Path, face_cfg: Settings, expected: dict[str, Any]
) -> None:
    (path,) = reframe_clips(far_face, [ClipSpan(1, 0.0, 4.0)], "9:16", cfg=face_cfg)

    keyframes = CropPlan.model_validate_json(path.read_bytes()).keyframes
    # The short-range model of before found it in none of the 40 samples.
    found = [k for k in keyframes if k.faces]
    assert len(keyframes) == 40 and len(found) >= 28
    for keyframe in found:
        (face,) = keyframe.faces
        center = FAR_X + face_center(expected, 5 + keyframe.t) * 400 / 1280
        assert (face.kind, face.subject) == ("face", True)
        # Within a fifth of the face's width.
        assert face.x + face.width / 2 == pytest.approx(center, abs=15)
        assert 60 <= face.width <= 100
    for keyframe in keyframes:
        assert keyframe.x == pytest.approx(894 - CROP_WIDTH / 2, abs=30)


def test_reframe_needs_the_face_model(tmp_path: Path) -> None:
    cfg = Settings(models_dir=tmp_path / "models")
    model = tmp_path / "models" / "face" / "blaze_face_full_range.tflite"

    with pytest.raises(StepError, match="the face model is not downloaded") as error:
        reframe_clips(tmp_path, [ClipSpan(1, 0.0, 4.0)], "9:16", cfg=cfg)

    assert f"{model} is missing" in str(error.value)


def test_existing_crop_plans_are_skipped_unless_forced(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    cfg = Settings(models_dir=tmp_path / "models")
    clip = ClipSpan(5, 0.0, 4.0)
    crop_path(tmp_path, 5).write_text("an old plan", encoding="utf-8")
    progress: list[float] = []

    # The model is missing, but no clip needs it.
    paths = reframe_clips(tmp_path, [clip], "1:1", cfg=cfg, on_progress=progress.append)

    assert paths == [tmp_path / "crop_5.json"]
    assert paths[0].read_text(encoding="utf-8") == "an old plan"
    assert progress == [1.0]
    assert "crop plan of clip 5 exists; skipping it" in caplog.messages
    with pytest.raises(StepError, match="the face model is not downloaded"):
        reframe_clips(tmp_path, [clip], "1:1", cfg=cfg, force=True)


def test_reframing_no_clips_needs_no_model(tmp_path: Path) -> None:
    progress: list[float] = []
    cfg = Settings(models_dir=tmp_path / "models")

    assert (
        reframe_clips(tmp_path, [], "9:16", cfg=cfg, on_progress=progress.append) == []
    )
    assert progress == [1.0]


def test_a_corrupt_face_model_is_a_step_error(tmp_path: Path) -> None:
    cfg = Settings(models_dir=tmp_path / "models")
    for model in FACE_MODELS:
        path = face_model_path(cfg, model)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not a model" * 100)

    with pytest.raises(StepError, match="cannot load the face model") as error:
        reframe_clips(tmp_path, [ClipSpan(1, 0.0, 4.0)], "9:16", cfg=cfg)

    assert "download_models.py --force" in str(error.value)


@pytest.mark.parametrize(
    ("size", "expected"),
    [((1280, 720), (640, 360)), ((1080, 1920), (360, 640)), ((320, 240), (320, 240))],
)
def test_frames_are_searched_at_most_640_pixels_wide_or_high(
    size: tuple[int, int], expected: tuple[int, int]
) -> None:
    assert analysis_size(*size) == expected


def test_find_faces_samples_10_frames_a_second_in_source_pixels(
    make_media: MakeMedia,
) -> None:
    video = make_media("faces.mp4", "-c:v", "libx264", size="1280x720", audio=False)
    frames: list[Frame] = []

    def detect(frame: Frame) -> list[FaceBox]:
        frames.append(frame)
        return [FaceBox(x=10.0, y=20.0, width=30.0, height=40.0, score=0.75)]

    # The 1 s video has 10 samples from 0 s; 2 more are asked for.
    faces = find_faces(video, 0.0, 12, (1280, 720), detect)

    scaled = FaceBox(x=20.0, y=40.0, width=60.0, height=80.0, score=0.75)
    assert faces == [[scaled]] * 10 + [[], []]
    assert [frame.shape for frame in frames] == [(360, 640, 3)] * 10
    assert all(frame.dtype == np.uint8 for frame in frames)


def test_mediapipe_has_no_clearcut_telemetry() -> None:
    # mediapipe 0.10.35 and later send usage logs to Google's Clearcut
    # (play.googleapis.com/log) from the C library; SPEC 2 allows no telemetry.
    (library,) = Path(mediapipe.__file__).parent.glob("tasks/c/libmediapipe.*")
    data = library.read_bytes()

    assert b"play.googleapis.com" not in data
    assert b"learcut" not in data
