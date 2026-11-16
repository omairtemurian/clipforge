"""Streaming a clip's sampled frames out of one ffmpeg run (steering: faster
reframe of long clips).

decode_frames (pipeline/faces) starts ffmpeg once per slice of frames and
waits for all of them, so decoding and face detection take turns. stream_frames
runs one ffmpeg for the whole span, and a reader thread keeps up to
QUEUE_FRAMES decoded frames ready while the caller works on the previous
ones; ffmpeg is stopped when the caller stops early.
"""

import logging
import queue
import shlex
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import IO

import numpy as np
import numpy.typing as npt

from clipforge.ffmpeg import FFmpegError, _arg, ffmpeg_bin

logger = logging.getLogger(__name__)

# Frames decoded ahead of the caller: 3 s at 10 a second, 21 MB at 640x360.
QUEUE_FRAMES = 30
# Marks the end of the frames in the queue.
_END = None

Frame = npt.NDArray[np.uint8]


def stream_frames(
    source: Path, start: float, count: int, size: tuple[int, int], fps: int
) -> Iterator[Frame]:
    """Yield up to count RGB frames [row, column, channel] of source from
    start seconds, sampled at fps frames a second and scaled to size (width,
    height): the frames that decode_frames returns, slice by slice.

    Raises FFmpegError if ffmpeg is missing or fails.
    """
    width, height = size
    command = [
        ffmpeg_bin(), "-nostdin", "-hide_banner", "-nostats", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-i", _arg(source), "-t", f"{count / fps:.3f}",
        "-map", "0:V:0", "-vf", f"fps={fps},scale={width}:{height}",
        "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]  # fmt: skip
    yield from stream_raw(command, size)


def stream_raw(
    command: list[str], size: tuple[int, int], channels: int = 3
) -> Iterator[Frame]:
    """Yield the frames [row, column, channel] of size (width, height) with
    channels bytes a pixel (rgb24: 3) that the ffmpeg command writes as
    rawvideo to its stdout, decoded ahead by a reader thread (module
    docstring); ffmpeg is stopped when the caller stops early.

    Raises FFmpegError if ffmpeg is missing or fails.
    """
    width, height = size
    logger.debug("running %s", shlex.join(command))
    frame_bytes = width * height * channels
    with tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=stderr
            )
        except FileNotFoundError as exc:
            raise FFmpegError(f"{command[0]} not found", command=command) from exc
        assert process.stdout is not None
        frames: queue.Queue[bytes | None] = queue.Queue(maxsize=QUEUE_FRAMES)
        stop = threading.Event()
        reader = threading.Thread(
            target=_read_frames,
            args=(process.stdout, frame_bytes, frames, stop),
            daemon=True,
        )
        reader.start()
        finished = False
        try:
            while (data := frames.get()) is not _END:
                yield np.frombuffer(data, dtype=np.uint8).reshape(
                    height, width, channels
                )
            finished = True
        finally:
            if not finished:
                stop.set()
                process.kill()
                _drain(frames)
            reader.join()
            status = process.wait()
            process.stdout.close()
        if finished and status != 0:
            stderr.seek(0)
            raise FFmpegError(
                f"{command[0]} exited with status {status}",
                command=command,
                stderr=stderr.read().decode("utf-8", errors="replace"),
            )


def _read_frames(
    stdout: IO[bytes],
    frame_bytes: int,
    frames: "queue.Queue[bytes | None]",
    stop: threading.Event,
) -> None:
    """Put each whole frame of frame_bytes read from stdout into frames,
    then _END; stop early if stop is set."""
    try:
        while not stop.is_set():
            data = stdout.read(frame_bytes)
            if len(data) < frame_bytes:
                break
            _put(frames, data, stop)
    finally:
        _put(frames, _END, stop)


def _put(
    frames: "queue.Queue[bytes | None]", item: bytes | None, stop: threading.Event
) -> None:
    """Put item into frames, waiting for room unless stop is set."""
    while not stop.is_set():
        try:
            frames.put(item, timeout=0.1)
            return
        except queue.Full:
            continue


def _drain(frames: "queue.Queue[bytes | None]") -> None:
    """Empty frames, so a reader waiting to put a frame can finish."""
    while True:
        try:
            frames.get_nowait()
        except queue.Empty:
            return
