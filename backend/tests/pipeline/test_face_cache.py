"""Tests of the job's face cache (pipeline/face_cache) and of reframe's
reuse of it, with its progress within a clip (pipeline/reframe_run;
steering: faster reframe of long clips)."""

import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from clipforge.config import Settings
from clipforge.models import FaceBox, SignalList, SourceMeta
from clipforge.pipeline import reframe_run
from clipforge.pipeline.face_cache import FACE_CACHE, FaceCache
from clipforge.pipeline.faces import Frame, find_faces
from clipforge.pipeline.reframe import ClipSpan
from clipforge.pipeline.reframe_run import reframe_clips
from clipforge.pipeline.step import META, SIGNALS, SOURCE, write_json

MakeMedia = Callable[..., Path]
FACE = FaceBox(x=100.0, y=60.0, width=40.0, height=40.0, score=0.9, mouth=0.1)


class CountingDetector:
    """A face detector that finds FACE (in 320x240 analysis pixels) in every
    frame and counts the frames it searched."""

    def __init__(self) -> None:
        self.frames = 0

    def __call__(self, frame: Frame) -> list[FaceBox]:
        self.frames += 1
        return [FACE]


@pytest.fixture
def job(make_media: MakeMedia, tmp_path: Path) -> Path:
    """A job with a 12 s 320x240 30 fps source and no scene cuts."""
    video = make_media("cache.mp4", "-c:v", "libx264", audio=False, duration=12.0)
    shutil.copy(video, tmp_path / SOURCE)
    meta = SourceMeta(
        title="cache",
        duration=12.0,
        width=320,
        height=240,
        fps=30.0,
        timeframe_start=0.0,
        timeframe_end=12.0,
    )
    write_json(tmp_path / META, meta)
    write_json(tmp_path / SIGNALS, SignalList([]))
    return tmp_path


@pytest.fixture
def detector(monkeypatch: pytest.MonkeyPatch) -> CountingDetector:
    """The CountingDetector that reframe_clips loads instead of MediaPipe."""
    detect = CountingDetector()

    @contextmanager
    def fake_detector(cfg: Settings) -> Iterator[CountingDetector]:
        yield detect

    monkeypatch.setattr(reframe_run, "face_detector", fake_detector)
    return detect


def test_the_cache_keeps_faces_per_source_frame(tmp_path: Path) -> None:
    cache = FaceCache(tmp_path, 30.0, (640, 360))
    cache.put(1.0, [FACE])
    cache.put(1.1, [])
    cache.save()

    loaded = FaceCache(tmp_path, 30.0, (640, 360))

    assert len(loaded) == 2
    # 1.0 s and 1.01 s are both source frame 30.
    assert loaded.get(1.01) == [FACE]
    assert loaded.get(1.1) == []
    assert loaded.get(1.2) is None
    copy = loaded.get(1.0)
    assert copy is not None
    copy[0].subject = True
    assert loaded.get(1.0) == [FACE]


@pytest.mark.parametrize(("fps", "analysis"), [(25.0, (640, 360)), (30.0, (320, 180))])
def test_a_cache_of_another_frame_rate_or_size_is_ignored(
    tmp_path: Path, fps: float, analysis: tuple[int, int]
) -> None:
    cache = FaceCache(tmp_path, 30.0, (640, 360))
    cache.put(1.0, [FACE])
    cache.save()

    assert len(FaceCache(tmp_path, fps, analysis)) == 0


def test_a_corrupt_cache_is_ignored(tmp_path: Path) -> None:
    (tmp_path / FACE_CACHE).write_text("{not json", encoding="utf-8")

    assert len(FaceCache(tmp_path, 30.0, (640, 360))) == 0


def test_find_faces_searches_only_the_frames_not_in_the_cache(job: Path) -> None:
    cache = FaceCache(job, 30.0, (320, 240))
    detect = CountingDetector()
    shares: list[float] = []

    first = find_faces(job / SOURCE, 2.0, 60, (320, 240), detect, cache=cache)
    again = find_faces(
        job / SOURCE,
        2.0,
        60,
        (320, 240),
        detect,
        cache=cache,
        on_progress=shares.append,
    )

    assert detect.frames == 60
    assert first == again == [[FACE]] * 60
    assert shares == [1.0]
    # 1 s further on, 50 of the 60 frames are known.
    find_faces(job / SOURCE, 3.0, 60, (320, 240), detect, cache=cache)
    assert detect.frames == 70


def test_reframe_reports_progress_within_a_clip_and_reuses_the_cache(
    job: Path, detector: CountingDetector
) -> None:
    shares: list[float] = []
    clips = [ClipSpan(1, 0.0, 10.0), ClipSpan(2, 5.0, 12.0)]

    reframe_clips(job, clips, "9:16", on_progress=shares.append)

    # Clip 1 is 100 samples; clip 2's from 5 to 10 s are clip 1's.
    assert detector.frames == 100 + 20
    assert (job / FACE_CACHE).is_file()
    assert shares == sorted(shares)
    assert shares[0] == 0.0 and shares[-1] == 1.0
    # Progress within clip 1 (10 of the 17 s) every 50 samples.
    assert pytest.approx(5 / 17) in shares

    reframe_clips(job, clips, "1:1", force=True)

    assert detector.frames == 120
