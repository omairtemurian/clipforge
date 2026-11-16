"""Motion spread (TASK-198): the share of the frame's columns that move."""

from pathlib import Path

import pytest
from clipforge.ffmpeg import run_ffmpeg
from clipforge.pipeline.motion_spread import motion_spread


@pytest.fixture(scope="module")
def half_moving(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 3 s 1280x720 video: stripes sliding across the left half, the
    right half still."""
    path = tmp_path_factory.mktemp("spread") / "half.mp4"
    video = (
        "color=size=1280x720:rate=30:duration=3,format=gray,"
        "geq=lum='128+100*sin(X/6+T*12)*lt(X,640)',format=yuv420p"
    )
    run_ffmpeg(["-f", "lavfi", "-i", video, "-c:v", "libx264", path])
    return path


def test_the_moving_share_of_the_columns_is_measured(half_moving: Path) -> None:
    samples = motion_spread(half_moving, 0.0, 3.0)
    assert len(samples) >= 10
    assert all(s.spread == pytest.approx(0.5, abs=0.06) for s in samples)
    assert samples == sorted(samples, key=lambda s: s.t)


def test_a_pair_across_a_scene_cut_does_not_move(half_moving: Path) -> None:
    samples = motion_spread(half_moving, 0.0, 3.0, [1.6])
    across = [s for s in samples if s.spread == 0.0]
    assert len(across) == 1 and 1.6 <= across[0].t < 1.6 + 0.5
