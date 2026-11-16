"""Tests for clipforge.timeline: the video track of a clip's segments and
moving the span that they cover."""

import pytest
from clipforge.models import Timeline, TrackItem
from clipforge.timeline import respan, timeline_of, video_items, with_segments


def test_video_items_play_the_segments_in_order() -> None:
    items = video_items([(30.0, 40.0), (5.0, 9.5)])

    assert items == [
        TrackItem(id="video-0", kind="source", start=30.0, end=40.0),
        TrackItem(id="video-1", kind="source", start=5.0, end=9.5),
    ]
    assert all(item.asset_id is None and item.props == {} for item in items)


def test_timeline_of_has_only_a_video_track() -> None:
    timeline = timeline_of([(1.0, 2.0)])

    assert timeline.video == video_items([(1.0, 2.0)])
    dumped = timeline.model_dump()
    assert [name for name, items in dumped.items() if items] == ["video"]


def test_with_segments_replaces_only_the_video_track() -> None:
    voiceover = TrackItem(id="vo-1", kind="source", start=0.0, end=1.0)
    tracks = Timeline(video=video_items([(1.0, 2.0)]), voiceover=[voiceover])

    moved = with_segments(tracks, [(3.0, 4.0)])

    assert moved.video == video_items([(3.0, 4.0)])
    assert moved.voiceover == [voiceover]
    assert tracks.video == video_items([(1.0, 2.0)])


@pytest.mark.parametrize(
    ("segments", "start", "end", "expected"),
    [
        ([(10.0, 12.5)], 9.0, 14.0, [(9.0, 14.0)]),
        ([(10.0, 12.5)], 11.0, 12.0, [(11.0, 12.0)]),
        ([(10.0, 12.0), (20.0, 25.0)], 8.0, 23.0, [(8.0, 12.0), (20.0, 23.0)]),
    ],
)
def test_respan_moves_the_first_start_and_the_last_end(
    segments: list[tuple[float, float]],
    start: float,
    end: float,
    expected: list[tuple[float, float]],
) -> None:
    assert respan(segments, start, end) == expected


def test_respan_rejects_an_emptied_segment() -> None:
    with pytest.raises(ValueError, match="not valid"):
        respan([(10.0, 12.0), (20.0, 25.0)], 12.0, 23.0)
