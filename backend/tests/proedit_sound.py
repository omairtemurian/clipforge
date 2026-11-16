"""Shared helpers of the Pro Edit sound tests (tests only): a silent source
video, the rendered sound as mono samples and its RMS levels."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import numpy.typing as npt
from clipforge.config import RenderSettings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import EdlItem
from clipforge.proedit.render.run import render_plan
from edl_fakes import plan
from proedit_render import base_of

FPS = 30
RATE = 48000
X264 = RenderSettings(encoder="libx264")
Samples = npt.NDArray[np.float64]


def silent_video(path: Path) -> Path:
    """Write a 6 s 1280x720 30 fps video whose sound is digital silence."""
    run_ffmpeg(
        ["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-f", "lavfi"]
        + ["-i", "anullsrc=r=48000:cl=stereo", "-t", "6", "-c:v", "libx264"]
        + ["-pix_fmt", "yuv420p", "-c:a", "aac", path]
    )
    return path


def render_sound(
    tmp_path: Path,
    source: Path,
    items: list[EdlItem],
    library: dict[str, Path] | None = None,
    speech: tuple[tuple[float, float], ...] = (),
    name: str = "sound",
    master: bool = False,
) -> Samples:
    """Render the test clip of source with items (proxy, libx264; its sound
    not mastered unless master) and return its sound, mono at RATE."""
    base = replace(base_of(source), speech=speech, sounds=library or {})
    output = render_plan(
        base,
        plan(items, "pro"),
        tmp_path / f"{name}.mp4",
        quality="proxy",
        settings=X264,
        master=master,
    )
    return decoded(output)


def decoded(media: Path) -> Samples:
    """The sound of media, mono float samples at RATE."""
    pcm = run_ffmpeg(
        ["-i", media, "-map", "0:a:0", "-ac", "1", "-ar", str(RATE)]
        + ["-f", "f32le", "pipe:1"]
    ).stdout
    return np.frombuffer(pcm, np.float32).astype(np.float64)


def levels_db(samples: Samples, window: int) -> Samples:
    """RMS level in dBFS of each window samples of samples."""
    count = len(samples) // window
    blocks = samples[: count * window].reshape(count, window)
    return 20 * np.log10(np.sqrt((blocks**2).mean(axis=1)) + 1e-9)


def level_db(samples: Samples, start: float, end: float) -> float:
    """RMS level in dBFS of samples from start to end seconds."""
    part = samples[round(start * RATE) : round(end * RATE)]
    return float(levels_db(part, len(part))[0])


def onset_frame(samples: Samples, first: int, last: int) -> int:
    """The first video frame from first to last whose RMS is within 30 dB of
    the loudest frame there (a sound's spike)."""
    levels = levels_db(samples, RATE // FPS)[first:last]
    return first + int(np.flatnonzero(levels > levels.max() - 30)[0])


def audible_span(samples: Samples, floor_db: float = -40) -> tuple[float, float]:
    """The first and last millisecond (in seconds) whose RMS is within
    -floor_db of the loudest millisecond of samples."""
    levels = levels_db(samples, RATE // 1000)
    loud = np.flatnonzero(levels > levels.max() + floor_db)
    return loud[0] / 1000, (loud[-1] + 1) / 1000
