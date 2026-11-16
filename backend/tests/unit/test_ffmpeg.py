"""Tests for how clipforge.ffmpeg runs ffmpeg and ffprobe and reports failures.

Everything runs the real binaries; test_ffmpeg_media.py covers what the
helpers report and write for real media.
"""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clipforge import config
from clipforge.ffmpeg import (
    STDERR_TAIL_CHARS,
    STDERR_TAIL_LINES,
    FFmpegError,
    extract_audio_wav,
    extract_frame,
    ffprobe_json,
    filter_value,
    probe_media,
    run_ffmpeg,
)

BACKEND = Path(__file__).resolve().parents[2]


def _frame(src: Path) -> Path:
    return extract_frame(src, src.with_name("frame.jpg"), 0.0)


def _wav(src: Path) -> Path:
    return extract_audio_wav(src, src.with_name("audio.wav"))


HELPERS: dict[str, tuple[str, Callable[[Path], object]]] = {
    "probe_media": ("ffprobe", probe_media),
    "ffprobe_json": ("ffprobe", ffprobe_json),
    "extract_frame": ("ffmpeg", _frame),
    "extract_audio_wav": ("ffmpeg", _wav),
}
each_helper = pytest.mark.parametrize(
    ("tool", "helper"), HELPERS.values(), ids=list(HELPERS)
)


@each_helper
def test_invalid_input_raises_ffmpeg_error_with_its_stderr(
    tool: str, helper: Callable[[Path], object], tmp_path: Path
) -> None:
    src = tmp_path / "notes.mp4"
    src.write_text("not a video\n")
    message = rf"^\S*{tool} exited with status \d+: "
    with pytest.raises(FFmpegError, match=message) as info:
        helper(src)
    error = info.value
    assert "Invalid data found when processing input" in error.stderr_tail
    assert str(error).endswith(error.stderr_tail)
    assert Path(error.command[0]).name == tool
    assert str(src) in error.command


@each_helper
def test_missing_input_raises_ffmpeg_error_with_its_stderr(
    tool: str, helper: Callable[[Path], object], tmp_path: Path
) -> None:
    with pytest.raises(FFmpegError, match=rf"(?s)^\S*{tool} exited.*No such file"):
        helper(tmp_path / "missing.mp4")


@each_helper
def test_missing_tool_raises_ffmpeg_error(
    tool: str,
    helper: Callable[[Path], object],
    sample_mp4: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clip = tmp_path / "sample.mp4"
    clip.symlink_to(sample_mp4)
    monkeypatch.setattr(config.settings, f"{tool}_bin", str(tmp_path / "missing"))
    with pytest.raises(FFmpegError, match="missing not found; install ffmpeg"):
        helper(clip)


def test_run_ffmpeg_prints_filter_reports_only_at_info_level(sample_mp4: Path) -> None:
    args: list[str | Path] = ["-i", sample_mp4, "-t", "5", "-map", "0:a:0"]
    args += ["-af", "loudnorm=print_format=json", "-f", "null", "-"]
    assert run_ffmpeg(args).stderr == b""
    report = run_ffmpeg(args, loglevel="info").stderr.decode()
    assert '"input_i"' in report
    assert "ffmpeg version" not in report


def test_filter_value_escapes_text_for_the_options_then_the_graph() -> None:
    assert filter_value("/data/clip_1.ass") == "/data/clip_1.ass"
    assert filter_value("a'b:c") == r"a\\\'b\\:c"
    assert filter_value("[a],b;c\\d e") == r"\[a\]\,b\;c\\\\d\\\ e"


@pytest.mark.parametrize(
    "text", ["/it's [1], a;b=c\\d:e %p.ass", "  spaced out  ", "\\'\\:"]
)
def test_ffmpeg_reads_a_filter_value_back_as_the_text(text: str) -> None:
    # The metadata filter adds the value to each frame, then prints it.
    graph = f"metadata=mode=add:key=k:value={filter_value(text)},metadata=mode=print"
    args = ["-f", "lavfi", "-i", "color=size=16x16:rate=1:duration=1"]

    result = run_ffmpeg([*args, "-vf", graph, "-f", "null", "-"], loglevel="info")

    assert re.findall(r"\] k=(.*)\n", result.stderr.decode()) == [text]


def test_relative_paths_that_look_like_options_are_files(
    sample_mp4: Path,
    expected: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "-clip.mp4").symlink_to(sample_mp4)
    monkeypatch.chdir(tmp_path)
    assert probe_media(Path("-clip.mp4")).duration == expected["media"]["duration"]
    extract_frame(Path("-clip.mp4"), Path("-thumb.jpg"), 1.0)
    assert (tmp_path / "-thumb.jpg").stat().st_size > 0


def test_ffmpeg_error_message_ends_with_the_stderr_tail() -> None:
    stderr = "\n".join(f"line {number}" for number in range(100)) + "\n"
    error = FFmpegError(
        "ffmpeg exited with status 1", command=["ffmpeg"], stderr=stderr
    )
    kept = [f"line {number}" for number in range(100 - STDERR_TAIL_LINES, 100)]
    assert error.stderr_tail.splitlines() == kept
    assert str(error) == "ffmpeg exited with status 1: " + "\n".join(kept)
    assert error.command == ["ffmpeg"]

    long_line = FFmpegError("failed", stderr="x" * 10_000 + "\nthe cause")
    assert len(long_line.stderr_tail) == STDERR_TAIL_CHARS
    assert long_line.stderr_tail.endswith("x\nthe cause")
    assert str(FFmpegError("no stderr")) == "no stderr"


def test_no_backend_code_runs_commands_through_a_shell() -> None:
    pattern = re.compile(r"shell\s*=\s*True")
    sources = sorted(BACKEND.rglob("*.py"))
    assert len(sources) > 10
    assert [path for path in sources if pattern.search(path.read_text())] == []
