"""Running ffmpeg while following how far its output has got.

ffmpeg's `-progress pipe:1` writes key=value lines to stdout about twice a
second (verified with ffmpeg 9.0): `out_time_us=<microseconds of output>`
("N/A" before the first frame) and, at the end of each report,
`progress=continue` or `progress=end`.
"""

import logging
import shlex
import subprocess
import tempfile
from collections.abc import Callable, Sequence

from clipforge.ffmpeg import Arg, FFmpegError, _arg, ffmpeg_bin
from clipforge.ffmpeg_args import spilled_args

logger = logging.getLogger(__name__)

OUT_TIME_KEY = "out_time_us"
END_LINE = "progress=end"


def progress_fraction(line: str, duration: float) -> float | None:
    """Return the share of duration (seconds) that a -progress line reports
    as written, within 0..1: 1.0 for progress=end, None for any other line,
    an out_time_us of "N/A" or a duration that is not positive."""
    text = line.strip()
    if text == END_LINE:
        return 1.0
    key, _, value = text.partition("=")
    if key != OUT_TIME_KEY or duration <= 0:
        return None
    try:
        seconds = int(value) / 1_000_000
    except ValueError:
        return None
    return min(max(seconds / duration, 0.0), 1.0)


def run_ffmpeg_progress(
    args: Sequence[Arg], duration: float, on_progress: Callable[[float], None]
) -> None:
    """Run `ffmpeg <args>` (as clipforge.ffmpeg.run_ffmpeg does: no stdin,
    -y, errors only) and pass on_progress the share of duration, the length
    of the output in seconds, written so far (progress_fraction).

    Long filter graphs are read from a file (ffmpeg_args.spilled_args).
    Raises FFmpegError if ffmpeg is missing or exits with a non-zero status;
    if on_progress raises, ffmpeg is killed and the error passed on.
    """
    with spilled_args([_arg(arg) for arg in args]) as spilled:
        command = [
            ffmpeg_bin(), "-nostdin", "-hide_banner", "-nostats", "-loglevel", "error",
            "-progress", "pipe:1", "-y", *spilled,
        ]  # fmt: skip
        _follow(command, duration, on_progress)


def _follow(
    command: list[str], duration: float, on_progress: Callable[[float], None]
) -> None:
    """Run command, an ffmpeg command line writing -progress to stdout, as
    run_ffmpeg_progress says."""
    logger.debug("running %s", shlex.join(command))
    with tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
            )
        except FileNotFoundError as exc:
            raise FFmpegError(f"{command[0]} not found", command=command) from exc
        with process:
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    fraction = progress_fraction(line, duration)
                    if fraction is not None:
                        on_progress(fraction)
            except BaseException:
                process.kill()
                raise
            status = process.wait()
        if status != 0:
            stderr.seek(0)
            raise FFmpegError(
                f"{command[0]} exited with status {status}",
                command=command,
                stderr=stderr.read().decode("utf-8", errors="replace"),
            )
