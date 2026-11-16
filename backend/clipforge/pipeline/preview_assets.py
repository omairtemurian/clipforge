"""Pictures and sound of a span of the source for the editor's timeline
(GET /clips/{id}/filmstrip and /clips/{id}/waveform).

The filmstrip is one JPEG row of small source frames, one every `interval`
seconds from the span's start; the waveform is the peak level of the
source's audio in buckets of 1/PEAKS_PER_SECOND seconds. Both are cached
in a directory under a name with a key of the span, so a second request
reads the file, and a new span of the same owner replaces the old file.
"""

import hashlib
import json
import math
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from clipforge.ffmpeg import probe_media, run_ffmpeg

# A thumbnail every second, at most MAX_TILES of them (longer spans space
# them out), each TILE_HEIGHT pixels tall (sharp on a 2x screen at 45 px).
FILMSTRIP_INTERVAL_S = 1.0
MAX_TILES = 240
TILE_HEIGHT = 90
FILMSTRIP_QUALITY = 5
PEAKS_PER_SECOND = 50
WAVEFORM_SAMPLE_RATE = 8_000
PCM_FULL_SCALE = 32_768.0
PEAK_DIGITS = 3

# One asset is made at a time, so two requests never write the same file.
_lock = threading.Lock()


class Waveform(BaseModel):
    """The audio level of a span of the source: peaks[i] is the loudest
    sample (0-1 of full scale) from start + i / peaks_per_second seconds on,
    for 1 / peaks_per_second seconds."""

    start: float
    end: float
    peaks_per_second: int = Field(gt=0)
    peaks: list[float]


@dataclass(frozen=True)
class Filmstrip:
    """A filmstrip image: count tiles in one row; tile i shows the source
    frame at start + i * interval seconds (tiles past the source are
    black)."""

    path: Path
    start: float
    end: float
    interval: float
    count: int


def filmstrip_layout(start: float, end: float) -> tuple[float, int]:
    """Return the (interval, count) of the tiles of a filmstrip from start to
    end seconds: one every FILMSTRIP_INTERVAL_S seconds, or fewer, evenly
    spaced, so there are at most MAX_TILES; always at least one."""
    span = max(0.0, end - start)
    interval = max(FILMSTRIP_INTERVAL_S, span / MAX_TILES)
    return interval, max(1, math.ceil(span / interval - 1e-9))


def filmstrip(
    source: Path, cache_dir: Path, owner: str, start: float, end: float
) -> Filmstrip:
    """Return the filmstrip of source from start to end seconds, made with
    ffmpeg unless it is cached in cache_dir (as <owner>-filmstrip-<key>.jpg,
    replacing owner's other filmstrips).

    Raises FFmpegError if ffmpeg cannot read the source's video.
    """
    interval, count = filmstrip_layout(start, end)
    key = _key("filmstrip", start, end, interval, count, TILE_HEIGHT)
    output = cache_dir / f"{owner}-filmstrip-{key}.jpg"
    strip = Filmstrip(output, start, end, interval, count)
    with _lock:
        if output.is_file():
            return strip
        cache_dir.mkdir(parents=True, exist_ok=True)
        graph = f"fps={1 / interval:.6f},scale=-2:{TILE_HEIGHT},tile={count}x1"
        run_ffmpeg(
            [
                "-ss", f"{start:.6f}", "-i", source, "-t", f"{end - start:.6f}",
                "-map", "0:V:0", "-an", "-vf", graph, "-frames:v", "1",
                "-update", "1", "-q:v", str(FILMSTRIP_QUALITY), output,
            ]
        )  # fmt: skip
        _drop_others(cache_dir, f"{owner}-filmstrip-*.jpg", output)
    return strip


def waveform(
    source: Path, cache_dir: Path, owner: str, start: float, end: float
) -> Waveform:
    """Return the waveform of source from start to end seconds, made with
    ffmpeg unless it is cached in cache_dir (as <owner>-waveform-<key>.json,
    replacing owner's other waveforms). A source without sound, or the part
    of the span past its end, has peaks of 0.

    Raises FFmpegError if ffmpeg cannot read the source.
    """
    key = _key("waveform", start, end, PEAKS_PER_SECOND, WAVEFORM_SAMPLE_RATE)
    output = cache_dir / f"{owner}-waveform-{key}.json"
    with _lock:
        if output.is_file():
            return Waveform.model_validate_json(output.read_bytes())
        cache_dir.mkdir(parents=True, exist_ok=True)
        samples = _pcm(source, start, end)
        wave = Waveform(
            start=start,
            end=end,
            peaks_per_second=PEAKS_PER_SECOND,
            peaks=peaks(samples, WAVEFORM_SAMPLE_RATE, end - start),
        )
        output.write_text(wave.model_dump_json())
        _drop_others(cache_dir, f"{owner}-waveform-*.json", output)
    return wave


def peaks(samples: np.ndarray, sample_rate: int, span: float) -> list[float]:
    """Return the peak of each 1/PEAKS_PER_SECOND s bucket of span seconds of
    16-bit samples (missing samples count as silence), 0-1 of full scale."""
    count = max(1, math.ceil(span * PEAKS_PER_SECOND - 1e-9))
    bucket = sample_rate // PEAKS_PER_SECOND
    levels = np.zeros(count * bucket, dtype=np.float32)
    used = samples[: levels.size].astype(np.float32)
    levels[: used.size] = np.abs(used) / PCM_FULL_SCALE
    top = levels.reshape(count, bucket).max(axis=1)
    return [round(float(value), PEAK_DIGITS) for value in np.clip(top, 0.0, 1.0)]


def _pcm(source: Path, start: float, end: float) -> np.ndarray:
    """Return the mono 16-bit samples of source's first audio stream from
    start to end seconds at WAVEFORM_SAMPLE_RATE; none if it has no sound."""
    if probe_media(source).audio_codec is None:
        return np.zeros(0, dtype="<i2")
    result = run_ffmpeg(
        [
            "-ss", f"{start:.6f}", "-i", source, "-t", f"{end - start:.6f}",
            "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(WAVEFORM_SAMPLE_RATE),
            "-f", "s16le", "pipe:1",
        ]
    )  # fmt: skip
    data = result.stdout[: len(result.stdout) // 2 * 2]
    return np.frombuffer(data, dtype="<i2")


def _key(*parts: object) -> str:
    """Return 12 hex digits of a hash of parts."""
    data = json.dumps([str(part) for part in parts]).encode()
    return hashlib.sha256(data).hexdigest()[:12]


def _drop_others(directory: Path, pattern: str, keep: Path) -> None:
    """Delete the files of directory matching pattern, except keep."""
    for old in directory.glob(pattern):
        if old != keep:
            old.unlink(missing_ok=True)
