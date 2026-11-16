"""Checks the committed pipeline fixture built by scripts/make_fixture.sh.

The tests read backend/tests/fixtures/sample.mp4 with ffprobe/ffmpeg and
verify that it matches expected.json: media properties, the speech and
laugh bursts in the audio track, and the path of the drawn face.
"""

import json
import math
import re
import subprocess
import sys
from array import array
from collections.abc import Sequence
from itertools import groupby, pairwise
from pathlib import Path
from typing import Any

import pytest
from clipforge.ffmpeg import ffmpeg_bin, ffprobe_bin

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "backend" / "tests" / "fixtures"
SAMPLE = FIXTURES / "sample.mp4"
SCRIPT = ROOT / "scripts" / "make_fixture.sh"
PCM_RATE = 16_000
FACE_TIMES = (0.0, 15.0, 30.0, 45.0, 59.9)

# The ffmpeg components and options make_fixture.sh uses, keyed by the
# `ffmpeg -h <topic>` page that documents them.
SCRIPT_OPTIONS = {
    "filter=testsrc2": ("size", "rate", "duration"),
    "filter=gblur": ("sigma",),
    "filter=color": ("color", "size", "rate", "duration"),
    "filter=format": ("pix_fmts",),
    "filter=geq": ("r", "g", "b", "a"),
    "filter=overlay": ("x", "y", "eof_action"),
    "filter=asplit": ("outputs",),
    "filter=atrim": ("start", "end"),
    "filter=volume": ("volume",),
    "filter=adelay": ("delays",),
    "filter=asetpts": ("expr",),
    "filter=amix": ("inputs", "normalize"),
    "filter=apad": ("whole_dur",),
    "filter=aeval": ("exprs", "channel_layout"),
    "encoder=libx264": ("preset", "crf"),
    "muxer=mp4": ("movflags",),
}

Burst = tuple[float, float]


def run(*args: str) -> bytes:
    """Run a command and return its stdout, raising if it fails."""
    tools = {"ffmpeg": ffmpeg_bin, "ffprobe": ffprobe_bin}
    command = [tools[args[0]](), *args[1:]] if args[0] in tools else args
    return subprocess.run(command, check=True, capture_output=True).stdout


def bursts(items: list[dict[str, float]]) -> list[Burst]:
    """Convert expected.json burst objects to (start, end) tuples."""
    return [(item["start"], item["end"]) for item in items]


def window_stats(pcm: Sequence[int], start: float, end: float) -> tuple[float, float]:
    """Return the RMS level in dBFS and the zero crossings per second of
    the samples between start and end seconds."""
    seg = pcm[int(start * PCM_RATE) : int(end * PCM_RATE)]
    energy = sum(x * x for x in seg) / len(seg)
    level = 10 * math.log10(energy / 32768**2) if energy else -math.inf
    crossings = sum((a < 0) != (b < 0) for a, b in pairwise(seg))
    return level, crossings * PCM_RATE / len(seg)


def is_skin(pixel: bytes, skin: Sequence[int]) -> bool:
    """True if an RGB pixel has the face skin tone, allowing for the head
    shading (down to 85 %) and colour conversion error."""
    pairs = zip(pixel, skin, strict=True)
    return all(0.75 * c - 4 <= v <= 1.05 * c + 4 for v, c in pairs)


def longest_run(flags: Sequence[bool]) -> tuple[int, int]:
    """Return the [start, end) index range of the longest run of True."""
    best, index = (0, 0), 0
    for flag, group in groupby(flags):
        length = len(list(group))
        if flag and length > best[1] - best[0]:
            best = (index, index + length)
        index += length
    return best


@pytest.fixture(scope="module")
def probe() -> dict[str, Any]:
    """ffprobe's description of sample.mp4."""
    out = run(
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json",
        str(SAMPLE),
    )  # fmt: skip
    data: dict[str, Any] = json.loads(out)
    return data


@pytest.fixture(scope="module")
def pcm() -> Sequence[int]:
    """The audio track decoded to 16 kHz mono signed 16-bit samples."""
    raw = run(
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(SAMPLE), "-map", "0:a:0",
        "-ac", "1", "-ar", str(PCM_RATE), "-c:a", "pcm_s16le", "-f", "s16le", "-",
    )  # fmt: skip
    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def test_ffprobe_matches_expected_media(
    probe: dict[str, Any], expected: dict[str, Any]
) -> None:
    media = expected["media"]
    streams = {stream["codec_type"]: stream for stream in probe["streams"]}
    assert len(probe["streams"]) == len(streams) == 2
    video, audio = streams["video"], streams["audio"]

    assert float(probe["format"]["duration"]) == pytest.approx(60, abs=0.1)
    assert media["duration"] == 60
    assert (video["codec_name"], video["width"], video["height"]) == ("h264", 1280, 720)
    assert (media["video_codec"], media["width"], media["height"]) == (
        "h264",
        1280,
        720,
    )
    assert video["pix_fmt"] == media["pix_fmt"] == "yuv420p"
    assert video["avg_frame_rate"] == f"{media['fps']}/1"
    assert int(video["nb_frames"]) == media["fps"] * media["duration"]
    assert audio["codec_name"] == media["audio_codec"] == "aac"
    assert int(audio["sample_rate"]) == media["sample_rate"]
    assert audio["channels"] == media["channels"]
    assert probe["format"]["tags"]["title"] == media["title"]


def test_expected_lists_three_laughs_and_a_face_path(expected: dict[str, Any]) -> None:
    laughs = expected["laughs"]
    assert len(laughs) == 3
    assert all(set(laugh) == {"start", "end"} for laugh in laughs)

    media, face = expected["media"], expected["face"]
    assert face["description"].strip()
    assert face["motion"] == "linear"
    start, end = face["start"], face["end"]
    assert (start["t"], end["t"]) == (0, media["duration"])
    assert start["center_x"] < end["center_x"]
    assert start["center_y"] == end["center_y"]
    for point in (start, end):
        assert (
            face["width"] / 2 <= point["center_x"] <= media["width"] - face["width"] / 2
        )
        assert (
            face["height"] / 2
            <= point["center_y"]
            <= media["height"] - face["height"] / 2
        )


def test_bursts_are_sorted_disjoint_and_inside_the_video(
    expected: dict[str, Any],
) -> None:
    speech = bursts(expected["speech"])
    laughs = bursts(expected["laughs"])
    duration = expected["media"]["duration"]
    assert speech == sorted(speech)
    assert laughs == sorted(laughs)
    for timeline in (speech, laughs, sorted(speech + laughs)):
        assert all(0 <= start < end <= duration for start, end in timeline)
        assert all(prev[1] < cur[0] for prev, cur in pairwise(timeline))


def test_audio_track_is_the_full_length(
    pcm: Sequence[int], expected: dict[str, Any]
) -> None:
    assert len(pcm) == pytest.approx(expected["media"]["duration"] * PCM_RATE, abs=1600)


def test_speech_bursts_are_tonal_and_quieter_than_laughs(
    pcm: Sequence[int], expected: dict[str, Any]
) -> None:
    speech = [
        window_stats(pcm, s + 0.05, e - 0.05) for s, e in bursts(expected["speech"])
    ]
    laughs = [
        window_stats(pcm, s + 0.1, e - 0.1) for s, e in bursts(expected["laughs"])
    ]
    for level, crossings in speech:
        assert -40 < level < -20
        assert crossings < 1000
    for level, crossings in laughs:
        assert level > -22
        assert crossings > 2000
    assert min(level for level, _ in laughs) - max(level for level, _ in speech) > 6


def test_audio_is_silent_between_bursts(
    pcm: Sequence[int], expected: dict[str, Any]
) -> None:
    events = sorted(bursts(expected["speech"]) + bursts(expected["laughs"]))
    edges = [
        0.0,
        *(t for event in events for t in event),
        expected["media"]["duration"],
    ]
    gaps = list(zip(edges[::2], edges[1::2], strict=True))
    assert len(gaps) == len(events) + 1
    for start, end in gaps:
        level, _ = window_stats(pcm, start + 0.05, end - 0.05)
        assert level < -50, (start, end, level)


@pytest.mark.parametrize("t", FACE_TIMES)
def test_face_moves_left_to_right_along_the_expected_path(
    t: float, expected: dict[str, Any]
) -> None:
    media, face = expected["media"], expected["face"]
    start, end = face["start"], face["end"]
    width = media["width"]
    row = run(
        "ffmpeg", "-nostdin", "-v", "error", "-ss", str(t), "-i", str(SAMPLE),
        "-frames:v", "1", "-vf", f"format=rgb24,crop={width}:1:0:{start['center_y']}",
        "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
    )  # fmt: skip
    assert len(row) == width * 3
    flags = [is_skin(row[3 * x : 3 * x + 3], face["skin_rgb"]) for x in range(width)]
    run_start, run_end = longest_run(flags)

    progress = (t - start["t"]) / (end["t"] - start["t"])
    center = start["center_x"] + (end["center_x"] - start["center_x"]) * progress
    assert (run_start + run_end - 1) / 2 == pytest.approx(center, abs=2)
    assert run_end - run_start == pytest.approx(face["width"], abs=10)


@pytest.mark.parametrize(("topic", "options"), SCRIPT_OPTIONS.items())
def test_script_uses_only_documented_ffmpeg_options(
    topic: str, options: tuple[str, ...]
) -> None:
    assert topic.split("=")[1] in SCRIPT.read_text()
    help_text = run("ffmpeg", "-hide_banner", "-h", topic).decode()
    for option in options:
        assert re.search(rf"^\s+-?{re.escape(option)}\s+<", help_text, re.M), option
