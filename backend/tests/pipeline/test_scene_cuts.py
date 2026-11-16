"""Tests of the scene cuts (SPEC 6.3) that PySceneDetect finds in a video.

The two_scenes video (conftest) is 4 s long and cuts from testsrc to SMPTE
color bars at 2 s; make_media's videos are one scene of testsrc.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from clipforge.pipeline.scene_cuts import detect_scene_cuts
from clipforge.pipeline.step import StepError

MakeMedia = Callable[..., Path]
FRAME_S = 1 / 30


def test_the_cut_between_two_scenes_is_found_within_a_frame(
    two_scenes: tuple[Path, float],
) -> None:
    video, cut = two_scenes
    assert detect_scene_cuts(video, 0.0, 4.0) == [pytest.approx(cut, abs=FRAME_S)]


def test_slices_find_the_cuts_of_one_pass_and_report_progress(
    two_scenes: tuple[Path, float],
) -> None:
    video, _ = two_scenes
    progress: list[float] = []
    cuts = detect_scene_cuts(video, 0.0, 4.0, slice_s=0.5, on_progress=progress.append)
    assert cuts == detect_scene_cuts(video, 0.0, 4.0)
    assert progress == [index / 8 for index in range(1, 9)]


@pytest.mark.parametrize(
    ("start", "end", "found"), [(1.0, 3.0, 1), (0.0, 1.5, 0), (2.5, 4.0, 0)]
)
def test_only_the_timeframe_is_searched(
    two_scenes: tuple[Path, float], start: float, end: float, found: int
) -> None:
    video, cut = two_scenes
    cuts = detect_scene_cuts(video, start, end)
    assert cuts == [pytest.approx(cut, abs=FRAME_S)] * found


def test_one_scene_has_no_cuts(make_media: MakeMedia) -> None:
    video = make_media("one_scene.mp4", "-c:v", "libx264", duration=3.0)
    assert detect_scene_cuts(video, 0.0, 3.0) == []


def test_a_missing_or_broken_video_is_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.mp4"
    with pytest.raises(StepError, match="cannot detect the scene cuts of .*missing"):
        detect_scene_cuts(missing, 0.0, 1.0)
    broken = tmp_path / "broken.mp4"
    broken.write_text("not a video", encoding="utf-8")
    with pytest.raises(StepError, match="cannot detect the scene cuts of .*broken"):
        detect_scene_cuts(broken, 0.0, 1.0)
