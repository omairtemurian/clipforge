"""Tests of clipforge.ffmpeg_progress: following ffmpeg's -progress report.

The runs use the real ffmpeg on lavfi sources.
"""

import re
from pathlib import Path

import pytest
from clipforge import config
from clipforge.ffmpeg import FFmpegError, probe_media
from clipforge.ffmpeg_progress import progress_fraction, run_ffmpeg_progress

TWO_SECONDS = ["-f", "lavfi", "-i", "testsrc=size=160x120:rate=25:duration=2"]


@pytest.mark.parametrize(
    ("line", "duration", "fraction"),
    [
        ("out_time_us=1000000\n", 4.0, 0.25),
        ("out_time_us=9000000", 4.0, 1.0),
        ("out_time_us=-5000", 4.0, 0.0),
        ("out_time_us=N/A", 4.0, None),
        ("out_time_us=1000000", 0.0, None),
        ("out_time_ms=1000000", 4.0, None),
        ("out_time=00:00:01.000000", 4.0, None),
        ("progress=continue", 4.0, None),
        ("progress=end\n", 4.0, 1.0),
        ("", 4.0, None),
    ],
)
def test_progress_fraction_reads_out_time_us_and_the_end(
    line: str, duration: float, fraction: float | None
) -> None:
    assert progress_fraction(line, duration) == fraction


def test_progress_rises_to_one_and_the_output_is_written(tmp_path: Path) -> None:
    output = tmp_path / "out.mp4"
    seen: list[float] = []
    run_ffmpeg_progress([*TWO_SECONDS, "-c:v", "libx264", output], 2.0, seen.append)
    assert seen and seen == sorted(seen)
    assert seen[-1] == 1.0
    assert probe_media(output).duration == pytest.approx(2.0, abs=0.1)


def test_a_failing_command_raises_with_ffmpeg_stderr(tmp_path: Path) -> None:
    missing = tmp_path / "missing.mp4"
    seen: list[float] = []
    with pytest.raises(FFmpegError, match="exited with status") as raised:
        run_ffmpeg_progress(["-i", missing, tmp_path / "out.mp4"], 1.0, seen.append)
    assert "No such file or directory" in raised.value.stderr_tail
    assert str(missing) in raised.value.command
    assert "-progress" in raised.value.command
    assert seen == []


def test_an_error_in_the_callback_stops_ffmpeg(tmp_path: Path) -> None:
    class Stop(Exception):
        pass

    def stop(fraction: float) -> None:
        raise Stop

    endless = ["-f", "lavfi", "-re", "-i", "testsrc=size=160x120:rate=25"]
    with pytest.raises(Stop):
        run_ffmpeg_progress([*endless, "-f", "null", "-"], 1.0, stop)


def test_a_missing_ffmpeg_raises_ffmpeg_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config.settings, "ffmpeg_bin", str(tmp_path / "no-ffmpeg"))
    with pytest.raises(FFmpegError, match=re.escape("no-ffmpeg not found")):
        run_ffmpeg_progress(TWO_SECONDS, 2.0, lambda fraction: None)
