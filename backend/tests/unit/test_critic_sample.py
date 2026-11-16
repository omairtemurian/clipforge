"""The frames the Pro Edit critic sees (SPEC-v3 3.7, TASK-222): the first
and last frame of every EDL item plus a 1 fps baseline, merged, in time
order and capped at max_frames (boundaries first, spread evenly)."""

import pytest
from clipforge.models import EdlItem
from clipforge.proedit.critic.sample import (
    BASELINE,
    FrameSample,
    frame_count,
    sample_frames,
    spread,
)
from edl_fakes import item

# A 10 s clip at 30 fps (frames 0..299): a zoom from 0.5 to 1.0 s (frames
# 15..29), a flash from 2.0 to 2.1 s (frames 60..62) and an SFX that runs
# past the end (first frame 297, last clamped to 299).
ITEMS = [
    item(3, "sfx", 9.9, 10.5),
    item(1, "zoom_punch", 0.5, 1.0),
    item(2, "flash", 2.0, 2.1),
]
BOUNDARIES = [15, 29, 60, 62, 297, 299]


def frames_of(samples: list[FrameSample]) -> list[int]:
    return [s.frame for s in samples]


def test_every_item_boundary_and_the_1_fps_baseline_are_sampled() -> None:
    samples = sample_frames(ITEMS, 10.0, 30, 24)

    assert frames_of(samples) == [
        0, 15, 29, 30, 60, 62, 90, 120, 150, 180, 210, 240, 270, 297, 299,
    ]  # fmt: skip
    assert [s.t for s in samples] == [n / 30 for n in frames_of(samples)]
    by_frame = {s.frame: s.reasons for s in samples}
    assert by_frame[15] == ("start of item 1 (zoom_punch)",)
    assert by_frame[29] == ("end of item 1 (zoom_punch)",)
    assert by_frame[60] == ("start of item 2 (flash)", BASELINE)
    assert by_frame[62] == ("end of item 2 (flash)",)
    assert by_frame[297] == ("start of item 3 (sfx)",)
    assert by_frame[299] == ("end of item 3 (sfx)",)
    assert by_frame[90] == (BASELINE,)


def test_items_that_share_a_frame_merge_their_reasons() -> None:
    items = [item(1, "flash", 1.0, 1.5), item(2, "shake", 1.0, 2.0)]

    samples = sample_frames(items, 3.0, 30, 24)

    assert frames_of(samples) == [0, 30, 44, 59, 60]
    assert samples[1].reasons == (
        "start of item 1 (flash)",
        "start of item 2 (shake)",
        BASELINE,
    )


@pytest.mark.parametrize(
    ("cap", "expected"),
    [
        (8, [0, 15, 29, 60, 62, 270, 297, 299]),
        (6, BOUNDARIES),
        (3, [15, 60, 299]),
        (1, [60]),
    ],
)
def test_the_cap_keeps_boundaries_first_then_spreads_the_baseline(
    cap: int, expected: list[int]
) -> None:
    samples = sample_frames(ITEMS, 10.0, 30, cap)

    assert frames_of(samples) == expected
    assert len(samples) <= cap


def test_a_plan_without_items_gets_the_baseline_only() -> None:
    no_items: list[EdlItem] = []

    samples = sample_frames(no_items, 2.5, 30, 24)

    assert frames_of(samples) == [0, 30, 60]
    assert [s.t for s in samples] == [0.0, 1.0, 2.0]
    assert frame_count(2.5, 30) == 75
    assert frame_count(0.01, 30) == 1


def test_spread_picks_evenly_including_both_ends() -> None:
    assert spread(range(10), 4) == [0, 3, 6, 9]
    assert spread([5, 6], 5) == [5, 6]
    assert spread([5, 6, 7], 0) == []
    assert spread([5, 6, 7, 8], 1) == [6]
