"""The minimal render and `clipforge run` (T07): from sample.mp4 to clip files.

Each run copies the fixture transcript into the job (so transcribe skips) and
answers curate with fixtures/llm_response.json. Its best candidate, with an
overall score of 71, is "My Body Had One Question in Yoga Class", 0.5-35.2 s,
which snap cuts at 34.35 s: 1.5 s after "cheese.", in the laugh after it.
The signals step runs YAMNet and reframe the face detector, so the runs are
slow tests, skipped when either model is not downloaded.
"""

import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest
from clipforge import cli, config, process
from clipforge.config import RenderSettings, Settings
from clipforge.db import ClipRow, JobRow, ProjectRow, init_db
from clipforge.encoders import VideoEncoder
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import Aspect, CropPlan, FaceBox, ProcessingSettings
from clipforge.pipeline.captions import captions_path
from clipforge.pipeline.reframe import ClipSpan, crop_path, plan_crop
from clipforge.pipeline.render import RenderError, render_clip
from clipforge.pipeline.step import load_json
from clipforge.testmode import ENV_VAR
from fakes import FIXTURES, FakeLLMClient
from sqlalchemy import Engine
from sqlmodel import Session, select

TRANSCRIPT = FIXTURES / "transcript.json"
BEST = ("My Body Had One Question in Yoga Class", 0.5, 34.35)
SIZES = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
# The crop windows of the aspects in the 1280x720 source.
CROPS = {"9:16": (404, 720), "1:1": (720, 720), "16:9": (1280, 720)}


def color_at(video: Path, time_s: float, x: float, y: float) -> tuple[int, ...]:
    """Return the RGB color of the frame at time_s at the fraction (x, y) of
    its width and height."""
    crop = f"format=rgb24,crop=1:1:iw*{x}:ih*{y}"
    result = run_ffmpeg(
        ["-ss", str(time_s), "-i", video, "-frames:v", "1", "-vf", crop]
        + ["-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    )
    return tuple(result.stdout)


def near(color: tuple[int, ...], expected: tuple[int, ...]) -> bool:
    """Return True if each channel of color is within 40 of expected."""
    return all(abs(a - b) <= 40 for a, b in zip(color, expected, strict=True))


def top_level_boxes(path: Path) -> list[str]:
    """Return the types of the top-level boxes of an mp4 file, in file order."""
    boxes = []
    with path.open("rb") as file:
        while header := file.read(8):
            size, kind = struct.unpack(">I4s", header)
            boxes.append(kind.decode("latin-1"))
            if size == 0:
                break
            if size == 1:
                (size,) = struct.unpack(">Q", file.read(8))
                size -= 8
            file.seek(size - 8, os.SEEK_CUR)
    return boxes


@pytest.mark.slow
@pytest.mark.usefixtures("yamnet_cfg", "face_cfg")
@pytest.mark.parametrize("aspect", ["9:16", "1:1", "16:9"])
def test_run_renders_the_best_clip_for_each_aspect(
    engine: Engine,
    data_dir: Path,
    sample_mp4: Path,
    aspect: Aspect,
    encoder: VideoEncoder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = config.settings.model_copy(update={"video_encoder": encoder})
    monkeypatch.setattr(config, "settings", cfg)
    # Without auto cut, the clip shows the source frame by frame (the CLI
    # test below has it on, the default).
    processing = ProcessingSettings(
        aspect=aspect, num_clips=1, auto_cut=False, auto_zoom=False
    )
    job_id = process.create_job(engine, str(sample_mp4), processing)

    clips = process.run_process_job(
        engine, job_id, llm=FakeLLMClient(), transcript=TRANSCRIPT
    )

    (clip,) = clips
    output = data_dir / "output" / str(clip.project_id) / f"{clip.id}.mp4"
    assert (clip.title, clip.start, clip.end) == BEST
    # Scored as comedy (3 laughs a minute) before snap: its laugh score is the
    # intensity of the 33.36-34.8 s laugh; energy peaks cover 2.451 s of the
    # candidate's 34.7 s.
    scores = clip.scores
    assert (scores.overall, scores.hook, scores.laugh) == (71, 88, 0.847)
    assert scores.energy == round(2.451 / 34.7, 3)
    assert (clip.status, clip.output_path) == ("rendered", str(output))
    exports = [output.with_suffix(".json"), output, output.with_suffix(".srt")]
    assert sorted(output.parent.iterdir()) == exports
    info = probe_media(output)
    assert (info.width, info.height) == SIZES[aspect]
    assert (info.video_codec, info.pix_fmt, info.audio_codec) == (
        "h264",
        "yuv420p",
        "aac",
    )
    assert info.duration == pytest.approx(BEST[2] - BEST[1], abs=0.2)
    assert info.fps == 30
    work = data_dir / "work" / str(job_id)
    plan = load_json(crop_path(work, clip.id), CropPlan, "reframe")
    assert (plan.clip_id, plan.start, plan.end, plan.aspect) == (
        clip.id,
        *BEST[1:],
        aspect,
    )
    assert ((plan.width, plan.height), len(plan.keyframes)) == (CROPS[aspect], 339)
    # One face: reframe chose fill, and the clip took it.
    assert (plan.layout, clip.layout) == ("fill", "fill")
    # libx264 writes its options into the stream; VideoToolbox does not.
    assert (b"crf=20.0" in output.read_bytes()) == (encoder == "libx264")
    boxes = top_level_boxes(output)
    assert boxes.index("moov") < boxes.index("mdat")
    # The frame 3 s into the clip, after the hook at the top, shows the
    # plan's window 3.5 s into the source (its keyframe 15); the points are
    # inside the source's color bars, above the captions in the middle.
    key = plan.keyframes[15]
    for u in (0.25, 0.75):
        source = color_at(sample_mp4, key.t, (key.x + u * plan.width) / 1280, 0.15)
        assert near(color_at(output, key.t - plan.start, u, 0.15), source)
    assert captions_path(work, clip.id).is_file()

    with Session(engine) as session:
        rows = session.exec(select(ClipRow)).all()
        job = session.get(JobRow, job_id)
        project = session.get(ProjectRow, clip.project_id)
    assert [(row.id, row.status, row.output_path) for row in rows] == [
        (clip.id, "rendered", str(output))
    ]
    assert job is not None and project is not None
    assert (job.kind, job.step, job.progress, job.status, job.error) == (
        "process",
        "render",
        1.0,
        "done",
        None,
    )
    assert (project.status, project.title, project.duration) == (
        "done",
        "ClipForge sample fixture",
        60.0,
    )


def test_render_clip_fails_and_leaves_no_file_when_the_clip_is_too_short(
    sample_mp4: Path, tmp_path: Path
) -> None:
    output = tmp_path / "7.mp4"
    output.write_bytes(b"an old render")

    no_faces: list[list[FaceBox]] = [[] for _ in range(40)]
    plan = plan_crop(ClipSpan(7, 58.0, 62.0), "1:1", (1280, 720), no_faces, [])

    # The source ends at 60 s, so the clip lasts 2 s instead of 4 s.
    with pytest.raises(RenderError, match=r"duration 2\.\d+s is not 4\.000s"):
        render_clip(sample_mp4, output, 58.0, 62.0, plan, "fill", RenderSettings())

    assert list(tmp_path.iterdir()) == []


@pytest.mark.slow
@pytest.mark.usefixtures("face_cfg")
def test_run_command_reports_clips_that_fail_to_render(
    engine: Engine,
    data_dir: Path,
    sample_mp4: Path,
    yamnet_cfg: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad_preset = RenderSettings(preset="no-such-preset")
    cfg = Settings(
        data_dir=data_dir,
        models_dir=yamnet_cfg.models_dir,
        render=bad_preset,
        video_encoder="libx264",
    )
    monkeypatch.setattr(config, "settings", cfg)
    monkeypatch.setenv(ENV_VAR, "1")
    argv = ["run", str(sample_mp4), "--num-clips", "2", "--fixtures-dir", str(FIXTURES)]

    assert cli.main(argv) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    error = "clipforge: error: 2 of 2 clips failed to render (ids: 1, 2)"
    assert error in captured.err.splitlines()
    with Session(engine) as session:
        clips = session.exec(select(ClipRow)).all()
        job = session.get(JobRow, 1)
    assert [(c.status, c.output_path) for c in clips] == [("failed", None)] * 2
    assert job is not None and (job.status, job.error) == ("done", None)
    assert list((data_dir / "output" / "1").iterdir()) == []


@pytest.mark.slow
@pytest.mark.usefixtures("face_cfg")
def test_clipforge_run_command_in_test_mode(
    sample_mp4: Path, yamnet_cfg: Settings, tmp_path: Path
) -> None:
    data = tmp_path / "data"
    command = [
        Path(sys.executable).with_name("clipforge"),
        "run",
        sample_mp4,
        "--num-clips",
        "1",
        "--fixtures-dir",
        FIXTURES,
    ]
    models = str(yamnet_cfg.models_dir)
    env = {**os.environ, "DATA_DIR": str(data), "MODELS_DIR": models, ENV_VAR: "1"}
    result = subprocess.run(
        command, env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    output = data / "output" / "1" / "1.mp4"
    assert result.stdout == f"{output}\n"
    # Auto cut (on by default) takes 3.44 s of silence out of the 33.85 s.
    assert probe_media(output).duration == pytest.approx(33.85 - 3.44, abs=0.2)
    log = (data / "work" / "1" / "job.log").read_text(encoding="utf-8")
    assert "INFO clipforge.pipeline.ingest: ingested 'ClipForge" in log
    assert "INFO clipforge.pipeline.snap: snapped 0.5-35.2s to 0.5-34.35s" in log
    reframed = re.search(
        r"INFO clipforge\.pipeline\.reframe_run: reframed clip 1 \(0\.5-34\.4s\) "
        r"in [\d.]+ s \([\d.]+ s per minute of video\): (.*)",
        log,
    )
    assert reframed is not None
    assert reframed.group(1) == (
        "faces in 339 of 339 frames, objects in 0, crop 404x720, "
        "layout fill, subject in 339"
    )
    captions = data / "work" / "1" / "captions_1.ass"
    assert f"(62 words, template karaoke_bold) to {captions}" in log
    rendered = f"rendered 0.5-34.4s as {output} (9:16, fill)"
    assert f"INFO clipforge.pipeline.render: {rendered}" in log
    # The subtitles show the 62 words of the captions in 25 lines, until
    # "cheese." ends at 32.85 s (28.98 s into the cut clip); a local file has
    # no channel to credit.
    srt = output.with_suffix(".srt")
    assert f"INFO clipforge.pipeline.export: wrote subtitles of clip 1 to {srt}" in log
    text = srt.read_text(encoding="utf-8")
    assert text.startswith("1\n00:00:00,000 --> 00:00:01,030\nHi everyone.\n\n2\n")
    assert text.endswith("\n25\n00:00:27,854 --> 00:00:28,984\nabout the cheese.\n\n")
    metadata = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert (metadata["title"], metadata["credit"]) == (BEST[0], None)
    engine = init_db(data)
    with Session(engine) as session:
        job = session.get(JobRow, 1)
        clip = session.get_one(ClipRow, 1)
    engine.dispose()
    assert clip.auto_cut
    # Auto zoom (on by default) punches in on the emphasis words and the new
    # sentences; "cheese." (32.43 s) is too close to the end at 34.35 s.
    assert clip.auto_zoom
    assert [k.t for k in clip.zoom_keyframes[1::4]] == [
        2.53,
        6.63,
        12.99,
        19.24,
        23.13,
        27.53,
        30.53,
    ]
    assert clip.cut_ranges[:3] == [(3.02, 3.33), (6.17, 6.63), (7.27, 7.58)]
    assert job is not None
    assert (job.status, job.log_path) == ("done", str(data / "work" / "1" / "job.log"))
