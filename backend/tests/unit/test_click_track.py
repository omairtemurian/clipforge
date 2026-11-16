"""Tests of click-to-track's pieces (pipeline/click_track, STEERING item 7b)
with fake frames and trackers; the tracking of a real video is in
pipeline/test_click_track_video.py."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from clipforge.models import CropPoint, FaceBox, TrackSeed
from clipforge.pipeline import click_track
from clipforge.pipeline.click_track import (
    Box,
    DetectorTracker,
    seed_box,
    simplify,
    sliced_frames,
    track_scene,
    track_size,
)
from clipforge.pipeline.detectors import Frame
from clipforge.pipeline.faces import SLICE_SAMPLES, sample_times
from clipforge.pipeline.step import StepError

BLANK: Frame = np.zeros((180, 320, 3), dtype=np.uint8)


def face(x: float, y: float, width: float, height: float) -> FaceBox:
    """A face box at x, y of width x height pixels."""
    return FaceBox(x=x, y=y, width=width, height=height, score=0.9)


def click(t: float, x: float, y: float) -> TrackSeed:
    """A click at x, y (frame fractions) t seconds into the source."""
    return TrackSeed(t=t, x=x, y=y, width=0, height=0)


class StillTracker:
    """A tracker that sees the subject where it started, or loses it."""

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.box: Sequence[float] = (0, 0, 0, 0)
        self.updates = 0

    def init(self, image: Frame, box: tuple[int, int, int, int]) -> None:
        self.box = box

    def update(self, image: Frame) -> tuple[bool, Sequence[float]]:
        self.updates += 1
        return self.ok, self.box


@pytest.fixture
def blank_frames(monkeypatch: pytest.MonkeyPatch) -> list[tuple[float, int]]:
    """Make decode_frames return blank frames; return its (start, count) calls."""
    calls: list[tuple[float, int]] = []

    def decode(source: Path, start: float, count: int, size: Any) -> Any:
        calls.append((start, count))
        return np.zeros((count, 180, 320, 3), dtype=np.uint8)

    monkeypatch.setattr(click_track, "decode_frames", decode)
    return calls


def test_frames_are_tracked_at_320_pixels_on_the_longer_side() -> None:
    assert track_size((1920, 1080)) == (320, 180)
    assert track_size((1080, 1920)) == (180, 320)
    assert track_size((1280, 720)) == (320, 180)
    assert track_size((200, 100)) == (200, 100)


def test_a_drawn_box_is_tracked_as_drawn() -> None:
    seed = TrackSeed(t=1, x=0.25, y=0.5, width=0.1, height=0.2)

    assert seed_box(seed, [face(0, 0, 320, 180)], (320, 180)) == (80, 90, 32, 36)


def test_a_click_picks_the_smallest_face_around_it() -> None:
    body = face(100, 20, 120, 160)
    head = face(140, 30, 40, 40)
    elsewhere = face(10, 10, 20, 20)

    box = seed_box(click(1, 0.5, 0.25), [body, head, elsewhere], (320, 180))

    assert box == (140, 30, 40, 40)


def test_a_click_without_a_face_tracks_a_square_kept_in_the_frame() -> None:
    assert seed_box(click(1, 0.5, 0.5), [face(0, 0, 20, 20)], (320, 180)) == (
        146.5,
        76.5,
        27.0,
        27.0,
    )
    assert seed_box(click(1, 0.01, 0.99), [], (320, 180)) == (0.0, 153.0, 27.0, 27.0)


def test_simplify_keeps_the_corners_of_the_path() -> None:
    line = [CropPoint(t=k, x=0.1 + 0.05 * k, y=0.5) for k in range(5)]
    wobble = [CropPoint(t=k, x=0.5 + (0.004 if k % 2 else 0), y=0.5) for k in range(5)]
    corner = [*line, CropPoint(t=5, x=0.25, y=0.5), CropPoint(t=6, x=0.2, y=0.5)]

    assert simplify(line) == [line[0], line[4]]
    assert simplify(wobble) == [wobble[0], wobble[4]]
    assert [point.t for point in simplify(corner)] == [0, 4, 6]
    assert simplify(line[:2]) == line[:2]


def test_frames_are_decoded_slice_by_slice_both_ways() -> None:
    times = [k / 10 for k in range(SLICE_SAMPLES + 3)]
    calls: list[tuple[float, int]] = []

    def decode(start: float, count: int) -> list[Frame]:
        calls.append((start, count))
        first = round(start * 10)
        missing = 1 if count == 3 else 0
        return [np.full((1, 1, 3), first + k, np.uint8) for k in range(count - missing)]

    forward = [
        None if f is None else int(f[0, 0, 0]) for f in sliced_frames(decode, times)
    ]
    backward = [
        None if f is None else int(f[0, 0, 0])
        for f in sliced_frames(decode, times, backward=True)
    ]

    assert forward == [*range(SLICE_SAMPLES + 2), None]
    assert backward == [None, *reversed(range(SLICE_SAMPLES + 2))]
    assert calls == [(0.0, 50), (5.0, 3), (5.0, 3), (0.0, 50)]


def test_a_still_subject_is_held_at_its_box_through_the_scene(
    blank_frames: list[tuple[float, int]],
) -> None:
    times = sample_times(10.0, 12.0)
    trackers = [StillTracker(), StillTracker()]

    keyframes, seed = track_scene(
        Path("source.mp4"),
        (1280, 720),
        times,
        TrackSeed(t=11.0, x=0.25, y=0.5, width=0.125, height=0.25),
        None,
        lambda: trackers.pop(),
    )

    assert keyframes == [
        CropPoint(t=10.0, x=0.3125, y=0.625),
        CropPoint(t=11.9, x=0.3125, y=0.625),
    ]
    assert seed == TrackSeed(t=11.0, x=0.25, y=0.5, width=0.125, height=0.25)
    assert blank_frames == [(11.0, 1), (10.0, 10), (11.1, 9)]


def test_a_lost_subject_holds_the_seed_box_center(
    blank_frames: list[tuple[float, int]],
) -> None:
    lost = StillTracker(ok=False)

    keyframes, _ = track_scene(
        Path("source.mp4"),
        (1280, 720),
        sample_times(0.0, 1.0),
        click(0.5, 0.75, 0.5),
        lambda frame: [],
        lambda: lost,
    )

    assert keyframes == [
        CropPoint(t=0.0, x=0.75, y=0.5),
        CropPoint(t=0.9, x=0.75, y=0.5),
    ]
    assert lost.updates == 9


def test_without_a_tracker_the_detector_follows_the_subject(
    blank_frames: list[tuple[float, int]],
) -> None:
    boxes = iter(
        [[face(150, 80, 20, 20)]] + [[face(150 + k, 80, 20, 20)] for k in range(9)]
    )

    keyframes, seed = track_scene(
        Path("source.mp4"),
        (320, 180),
        sample_times(0.0, 1.0),
        click(0.0, 0.5, 0.5),
        lambda frame: next(boxes),
        lambda: None,
    )

    assert seed == TrackSeed(t=0.0, x=0.4688, y=0.4444, width=0.0625, height=0.1111)
    assert keyframes[0].t == 0.0 and keyframes[-1].t == 0.9
    with pytest.raises(StepError, match="no OpenCV tracker"):
        track_scene(
            Path("source.mp4"),
            (320, 180),
            [0.0, 0.1],
            click(0, 0.5, 0.5),
            None,
            lambda: None,
        )


def test_the_detector_tracker_follows_the_nearest_box_and_loses_jumps() -> None:
    found: list[list[FaceBox]] = [
        [face(200, 10, 20, 20), face(104, 52, 20, 20)],
        [face(300, 50, 20, 20)],
        [],
    ]
    tracker = DetectorTracker(lambda frame: found.pop(0))
    tracker.init(BLANK, (100, 50, 20, 20))

    near: tuple[bool, Box] = tracker.update(BLANK)  # type: ignore[assignment]
    jump = tracker.update(BLANK)
    empty = tracker.update(BLANK)

    assert near == (True, (104.0, 52.0, 20.0, 20.0))
    assert jump == (False, (104.0, 52.0, 20.0, 20.0))
    assert empty[0] is False


def test_a_seed_frame_that_cannot_be_decoded_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        click_track, "decode_frames", lambda *args: np.zeros((0, 180, 320, 3), np.uint8)
    )

    with pytest.raises(StepError, match="no frame of the source at 1.000 s"):
        track_scene(Path("s.mp4"), (320, 180), [1.0], click(1, 0.5, 0.5), None)
