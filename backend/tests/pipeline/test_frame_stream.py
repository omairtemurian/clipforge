"""Tests of streaming a clip's sampled frames from one ffmpeg run
(pipeline/frame_stream)."""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from clipforge.ffmpeg import FFmpegError
from clipforge.pipeline.faces import SAMPLE_FPS, decode_frames
from clipforge.pipeline.frame_stream import stream_frames

MakeMedia = Callable[..., Path]


@pytest.fixture(scope="module")
def video(make_media: MakeMedia) -> Path:
    """A 3 s 320x240 testsrc video."""
    return make_media("stream.mp4", "-c:v", "libx264", audio=False, duration=3.0)


def test_streamed_frames_are_the_decoded_ones(video: Path) -> None:
    streamed = list(stream_frames(video, 0.5, 20, (160, 120), SAMPLE_FPS))
    decoded = decode_frames(video, 0.5, 20, (160, 120))

    assert len(streamed) == 20
    assert all(frame.shape == (120, 160, 3) for frame in streamed)
    assert np.array_equal(np.stack(streamed), decoded)


def test_the_stream_ends_with_the_video(video: Path) -> None:
    # 2.5 s from 1 s leaves 2 s: 20 frames.
    assert len(list(stream_frames(video, 1.0, 25, (32, 24), SAMPLE_FPS))) == 20


def test_stopping_early_stops_ffmpeg_without_an_error(video: Path) -> None:
    frames = stream_frames(video, 0.0, 30, (32, 24), SAMPLE_FPS)

    first = [next(frames) for _ in range(3)]
    frames.close()

    assert len(first) == 3


def test_a_missing_source_is_an_ffmpeg_error(tmp_path: Path) -> None:
    with pytest.raises(FFmpegError, match="exited with status"):
        list(stream_frames(tmp_path / "missing.mp4", 0.0, 5, (32, 24), SAMPLE_FPS))
