"""Golden isolation regression of the normal pipeline (SPEC-v3 0.13, TASK-202).

Pro Edit must never change what the normal pipeline makes. This test runs
the v1 fixture (sample.mp4) through the whole normal pipeline with the
default processing settings (one clip; the fixture transcript and the
canned LLM reply, as in test_run_minimal) and compares the rendered clip
with fixtures/golden_normal_pipeline.json, captured from main before any
Pro Edit code:

- the ffprobe stream parameters (codecs, size, frame rate, frame count,
  durations, pixel format, audio rate/channels) must be equal;
- the SHA-256 of the decoded yuv420p frame at 1 s, 5 s, 10 s and 0.5 s
  before the end must be equal (any change of crop, zoom, caption, color or
  timing changes them);
- the audio RMS (dBFS) of each 0.5 s window must be within RMS_TOLERANCE_DB
  of the golden one. The AAC stream decodes the same way every time, so the
  tolerance only absorbs float rounding; any mix, loudness or cut change
  moves windows by far more.

The render uses libx264, which is deterministic, because the default
encoder depends on the machine (VideoToolbox on Apple silicon). The golden
depends on the ffmpeg build (its version is stored for diagnosis).
Regenerate it only with a documented decision in docs/decisions.md:
CLIPFORGE_REGENERATE_GOLDEN=1 uv run pytest <this file> rewrites the file
and skips.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from clipforge import config, process
from clipforge.ffmpeg import ffprobe_json, run_ffmpeg
from clipforge.models import ProcessingSettings
from fakes import FIXTURES, FakeLLMClient
from sqlalchemy import Engine

GOLDEN = FIXTURES / "golden_normal_pipeline.json"
TRANSCRIPT = FIXTURES / "transcript.json"
REGENERATE = "CLIPFORGE_REGENERATE_GOLDEN"
FRAME_TIMES_S = (1.0, 5.0, 10.0)
END_OFFSET_S = 0.5
RMS_WINDOW_S = 0.5
RMS_TOLERANCE_DB = 0.05
SILENCE_DBFS = -120.0
VIDEO_KEYS = (
    "codec_name",
    "profile",
    "width",
    "height",
    "pix_fmt",
    "r_frame_rate",
    "avg_frame_rate",
    "nb_frames",
    "duration",
)
AUDIO_KEYS = (
    "codec_name",
    "sample_rate",
    "channels",
    "channel_layout",
    "duration",
)


def stream_params(path: Path) -> dict[str, dict[str, Any]]:
    """Return the VIDEO_KEYS of the first video stream and the AUDIO_KEYS of
    the first audio stream of path, as ffprobe reports them."""
    streams = ffprobe_json(path)["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    audio = next(s for s in streams if s["codec_type"] == "audio")
    return {
        "video": {key: video.get(key) for key in VIDEO_KEYS},
        "audio": {key: audio.get(key) for key in AUDIO_KEYS},
    }


def frame_hash(path: Path, time_s: float) -> str:
    """Return the SHA-256 of the decoded yuv420p frame of path at time_s."""
    result = run_ffmpeg(
        ["-ss", f"{time_s:.3f}", "-i", path, "-frames:v", "1"]
        + ["-f", "rawvideo", "-pix_fmt", "yuv420p", "pipe:1"]
    )
    assert result.stdout, f"no frame at {time_s:.3f} s"
    return hashlib.sha256(result.stdout).hexdigest()


def rms_profile(path: Path, sample_rate: int, channels: int) -> list[float]:
    """Return the RMS in dBFS (2 decimals, SILENCE_DBFS for digital silence)
    of each RMS_WINDOW_S window of path's first audio stream, all channels
    together; a last partial window counts too."""
    result = run_ffmpeg(
        ["-i", path, "-map", "0:a:0", "-f", "f32le", "-c:a", "pcm_f32le", "pipe:1"]
    )
    samples = np.frombuffer(result.stdout, dtype="<f4").astype(np.float64)
    window = int(round(RMS_WINDOW_S * sample_rate)) * channels
    profile = []
    for start in range(0, len(samples), window):
        chunk = samples[start : start + window]
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        level = 20 * np.log10(rms) if rms > 0 else SILENCE_DBFS
        profile.append(round(max(float(level), SILENCE_DBFS), 2))
    return profile


def measure(path: Path) -> dict[str, Any]:
    """Return the golden record of the rendered clip at path."""
    streams = stream_params(path)
    end = float(streams["video"]["duration"]) - END_OFFSET_S
    times = [*FRAME_TIMES_S, round(end, 3)]
    audio = streams["audio"]
    return {
        "streams": streams,
        "frames": {f"{t:.3f}": frame_hash(path, t) for t in times},
        "rms_window_s": RMS_WINDOW_S,
        "rms_dbfs": rms_profile(path, int(audio["sample_rate"]), audio["channels"]),
    }


def ffmpeg_version() -> str:
    """Return the first line of `ffmpeg -version`."""
    result = run_ffmpeg(["-version"])
    return result.stdout.decode("utf-8", errors="replace").splitlines()[0]


@pytest.mark.slow
@pytest.mark.usefixtures("yamnet_cfg", "face_cfg")
def test_the_normal_pipeline_renders_the_golden_clip(
    engine: Engine,
    data_dir: Path,
    sample_mp4: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = config.settings.model_copy(update={"video_encoder": "libx264"})
    monkeypatch.setattr(config, "settings", cfg)
    job_id = process.create_job(
        engine, str(sample_mp4), ProcessingSettings(num_clips=1)
    )

    (clip,) = process.run_process_job(
        engine, job_id, llm=FakeLLMClient(), transcript=TRANSCRIPT
    )

    assert clip.output_path is not None
    record = {
        "clip": {"title": clip.title, "start": clip.start, "end": clip.end},
        **measure(Path(clip.output_path)),
    }
    if os.environ.get(REGENERATE) == "1":
        golden = {"ffmpeg_version": ffmpeg_version(), **record}
        GOLDEN.write_text(json.dumps(golden, indent=2) + "\n", encoding="utf-8")
        pytest.skip(f"{REGENERATE}=1: wrote {GOLDEN.name}; log the decision")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    now = ffmpeg_version()
    note = ""
    if golden["ffmpeg_version"] != now:
        note = f"the golden was made with {golden['ffmpeg_version']!r}, not {now!r}"
    assert record["clip"] == golden["clip"]
    assert record["streams"] == golden["streams"]
    assert record["frames"] == golden["frames"], note
    assert golden["rms_window_s"] == RMS_WINDOW_S
    assert len(record["rms_dbfs"]) == len(golden["rms_dbfs"])
    assert record["rms_dbfs"] == pytest.approx(
        golden["rms_dbfs"], abs=RMS_TOLERANCE_DB
    ), note
