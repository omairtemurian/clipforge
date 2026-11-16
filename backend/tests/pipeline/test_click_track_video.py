"""Tests of click-to-track on a real video (pipeline/click_track, STEERING
item 7b): a square that moves right at 120 px/s through a 640x360 video."""

from pathlib import Path

import pytest
from clipforge.models import TrackSeed
from clipforge.pipeline.click_track import track_scene
from clipforge.pipeline.faces import sample_times
from moving_square import make_moving_square, square_x


@pytest.fixture(scope="module")
def moving_square(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The 4 s moving square video (tests/moving_square)."""
    return make_moving_square(tmp_path_factory.mktemp("track") / "square.mp4")


def test_a_click_on_the_square_follows_it_through_the_scene(
    moving_square: Path,
) -> None:
    clicked = TrackSeed(t=2.0, x=round(square_x(2.0), 4), y=0.5, width=0, height=0)

    keyframes, seed = track_scene(
        moving_square, (640, 360), sample_times(0.0, 4.0), clicked, None
    )

    assert seed == TrackSeed(t=2.0, x=0.4422, y=0.425, width=0.0844, height=0.15)
    assert keyframes[0].t == 0.0 and keyframes[-1].t == 3.9
    assert all(abs(point.y - 0.5) < 0.01 for point in keyframes)
    inner = [point for point in keyframes if 0.5 <= point.t <= 3.5]
    assert len(inner) >= 5
    assert all(abs(point.x - square_x(point.t)) < 0.05 for point in inner)
    assert [point.x for point in keyframes] == sorted(point.x for point in keyframes)
    assert keyframes[-1].x - keyframes[0].x > 0.6
