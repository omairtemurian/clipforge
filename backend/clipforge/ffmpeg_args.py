"""Keeping ffmpeg's command line short (steering: long-clip render argv).

A long clip's filter graph (a crop x expression with one term per reframe
keyframe, thousands of them for a 20 min clip) can pass the operating
system's limit on the size of a command line (ARG_MAX: 1 MiB on macOS, with
the environment), and exec then fails with E2BIG ("Argument list too
long"). ffmpeg reads the value of any option from a file when its name is
prefixed with a slash (ffmpeg 7.0+; `-/filter_complex graph.txt`, verified
with ffmpeg 9.0.2: the old -filter_complex_script is gone), so spilled_args
writes each long filter option value to a temporary file and passes that.
"""

import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

# Option values longer than this (in UTF-8 bytes) go through a file.
MAX_INLINE_BYTES = 4_096
# The options whose values are filter graphs, which can grow with a clip.
FILTER_OPTIONS = ("-filter_complex", "-lavfi", "-vf", "-af", "-filter")


def is_filter_option(arg: str) -> bool:
    """True if arg names an option whose value is a filter graph (-vf,
    -filter_complex, ..., or -filter:v and other per-stream forms)."""
    name = arg.split(":", 1)[0]
    return name in FILTER_OPTIONS


@contextmanager
def spilled_args(args: Sequence[str]) -> Iterator[list[str]]:
    """Yield args with the value of each filter option longer than
    MAX_INLINE_BYTES written to a file in a temporary directory, and the
    option renamed to read it from there (`-/filter_complex <file>`). The
    files are removed when the block ends."""
    long_at = [
        index + 1
        for index, arg in enumerate(args[:-1])
        if is_filter_option(arg)
        and len(args[index + 1].encode("utf-8")) > MAX_INLINE_BYTES
    ]
    if not long_at:
        yield list(args)
        return
    with tempfile.TemporaryDirectory(prefix="clipforge-ffmpeg-") as directory:
        spilled = list(args)
        for number, index in enumerate(long_at):
            path = Path(directory) / f"option-{number}.txt"
            path.write_text(args[index], encoding="utf-8")
            spilled[index - 1] = f"-/{args[index - 1].lstrip('-')}"
            spilled[index] = str(path)
        yield spilled
