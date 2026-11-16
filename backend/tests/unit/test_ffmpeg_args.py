"""Tests that long filter graphs reach ffmpeg through a file, not the command
line (ffmpeg_args.spilled_args; steering: `[Errno 7] Argument list too long`
rendering a 20 min clip)."""

import subprocess
from pathlib import Path
from typing import Any

import pytest
from clipforge import ffmpeg
from clipforge.ffmpeg import run_ffmpeg
from clipforge.ffmpeg_args import MAX_INLINE_BYTES, is_filter_option, spilled_args
from clipforge.ffmpeg_progress import run_ffmpeg_progress


def long_graph(size: int) -> str:
    """A valid -filter_complex graph of more than size bytes: a crop whose x
    is 0 padded with spaces (ffmpeg's expression parser drops them)."""
    return f"[0:v]crop=w=32:h=32:x='0{' ' * size}':y=0[v]"


def test_short_arguments_stay_on_the_command_line() -> None:
    args = ["-i", "in.mp4", "-filter_complex", "[0:v]scale=2:2[v]", "out.mp4"]

    with spilled_args(args) as spilled:
        assert spilled == args


def test_a_long_filter_graph_is_read_from_a_file_removed_afterwards() -> None:
    graph = long_graph(MAX_INLINE_BYTES * 3)
    args = ["-i", "in.mp4", "-filter_complex", graph, "-map", "[v]", "out.mp4"]

    with spilled_args(args) as spilled:
        assert spilled[:2] == ["-i", "in.mp4"]
        assert spilled[2] == "-/filter_complex"
        path = Path(spilled[3])
        assert path.read_text(encoding="utf-8") == graph
        assert spilled[4:] == ["-map", "[v]", "out.mp4"]

    assert not path.exists()
    assert args[3] == graph


@pytest.mark.parametrize(
    ("option", "spills"),
    [
        ("-vf", True),
        ("-af", True),
        ("-filter:v", True),
        ("-filter:a:0", True),
        ("-lavfi", True),
        ("-metadata", False),
        ("-i", False),
    ],
)
def test_only_filter_options_are_spilled(option: str, spills: bool) -> None:
    assert is_filter_option(option) is spills
    args = [option, "x" * (MAX_INLINE_BYTES + 1)]

    with spilled_args(args) as spilled:
        assert (spilled[0] == f"-/{option[1:]}") is spills


def test_run_ffmpeg_renders_a_graph_longer_than_the_command_line_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 2 MB: more than macOS's ARG_MAX (1 MiB) and Linux's 128 KiB per argument.
    graph = long_graph(2_000_000)
    commands: list[list[str]] = []
    real_run = subprocess.run

    def recording_run(command: list[str], **kwargs: Any) -> Any:
        commands.append(command)
        return real_run(command, **kwargs)

    monkeypatch.setattr(ffmpeg.subprocess, "run", recording_run)
    output = tmp_path / "out.mp4"

    run_ffmpeg(
        ["-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=0.4"]
        + ["-filter_complex", graph, "-map", "[v]", output]
    )

    assert output.stat().st_size > 0
    (command,) = commands
    assert "-/filter_complex" in command
    assert sum(len(arg) for arg in command) < 10_000


def test_run_ffmpeg_progress_reads_a_long_graph_from_a_file(tmp_path: Path) -> None:
    output = tmp_path / "out.mp4"
    shares: list[float] = []

    run_ffmpeg_progress(
        ["-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=0.4"]
        + ["-filter_complex", long_graph(2_000_000), "-map", "[v]", output],
        0.4,
        shares.append,
    )

    assert output.stat().st_size > 0
    assert shares[-1] == 1.0
