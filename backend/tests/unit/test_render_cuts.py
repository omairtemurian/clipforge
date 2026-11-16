"""Unit tests of a render's cuts (SPEC 6.10, 6.11): cut edges on frames
(frame_cuts.frame_ms, cut_spans with fps), the parts a render keeps
(frame_cuts.kept_spans) and the filter graph that cuts and joins them
(render_graph)."""

from pathlib import Path

import pytest
from clipforge.config import RenderSettings
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.frame_cuts import cut_spans, frame_ms, kept_spans
from clipforge.pipeline.layouts import layout_graph
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import RenderError, render_clip
from clipforge.pipeline.render_graph import (
    audio_graph,
    clip_graph,
    cut_graph,
    subtitles_filter,
)

# Cuts of the clip from 10.0 to 12.99 s, whose end is not on a 30 fps frame.
CUTS = [(9.0, 10.21), (11.0, 11.84), (11.85, 11.86), (12.5, 13.0)]
# Clip A of the fixture (0.5-34.35 s) and its filler cuts.
CLIP_A = (0.5, 34.35)
CUTS_A = [(6.2, 7.55), (22.6, 24.15)]
SPANS = [(0.0, 1.5), (2.0, 10 / 3)]
SIZE = (1080, 1920)
PLAN = plan_crop(
    ClipSpan(1, 10.0, 12.0), "9:16", (1280, 720), [[] for _ in sample_times(10, 12)], []
)
AUDIO_CUT = (
    "[0:a:0]asplit=2[cut_a0][cut_a1];"
    "[cut_a0]atrim=start=0.000000:end=1.500000,asetpts=PTS-STARTPTS[kept_a0];"
    "[cut_a1]atrim=start=2.000000:end=3.333333,asetpts=PTS-STARTPTS[kept_a1];"
)


@pytest.mark.parametrize(
    ("time", "fps", "expected"),
    [
        (0, 30, 0),
        (16, 30, 0),
        (17, 30, 33),
        (840, 30, 833),
        (1250, 30, 1267),
        (1700, 30, 1700),
        (1019, 25, 1000),
        (1021, 25, 1040),
    ],
)
def test_frame_ms_is_the_nearest_frame(time: int, fps: int, expected: int) -> None:
    assert frame_ms(time, fps) == expected


def test_cut_spans_with_fps_move_their_inner_edges_to_frames() -> None:
    assert cut_spans(10.0, 12.99, CUTS) == [
        (0, 210),
        (1000, 1840),
        (1850, 1860),
        (2500, 2990),
    ]
    # 1840 is on frame 55 (1833 ms), and 1850-1860 on frame 56: that cut is
    # gone; the clip's start and end stay where they are.
    assert cut_spans(10.0, 12.99, CUTS, 30) == [(0, 200), (1000, 1833), (2500, 2990)]


def test_kept_spans_hold_whole_frames_between_the_cuts() -> None:
    assert kept_spans(10.0, 12.99, CUTS, 30) == [(6 / 30, 30 / 30), (55 / 30, 75 / 30)]
    assert kept_spans(10.0, 12.99, CUTS[:1], 30) == [(0.2, 2.99)]
    assert kept_spans(10.0, 12.99, [], 30) == [(0.0, 2.99)]
    assert kept_spans(10.0, 12.99, [(9.0, 14.0)], 30) == []


def test_kept_spans_of_clip_a_leave_out_its_filler_cuts() -> None:
    spans = kept_spans(*CLIP_A, CUTS_A, 30)

    assert spans == [(0.0, 5.7), (212 / 30, 22.1), (710 / 30, 33.85)]
    assert sum(end - start for start, end in spans) == pytest.approx(30.9167, abs=1e-4)


def test_cut_graph_of_audio_alone_trims_each_part_and_concats() -> None:
    assert cut_graph(SPANS, ("[0:a:0]", "[acut]")) == (
        f"{AUDIO_CUT}[kept_a0][kept_a1]concat=n=2:v=0:a=1[acut]"
    )


def test_cut_graph_joins_each_part_of_the_video_with_its_audio() -> None:
    assert cut_graph(SPANS, ("[0:a:0]", "[acut]"), ("[framed]", "[cut]")) == (
        "[framed]split=2[cut_v0][cut_v1];"
        "[cut_v0]trim=start=0.000000:end=1.500000,setpts=PTS-STARTPTS[kept_v0];"
        "[cut_v1]trim=start=2.000000:end=3.333333,setpts=PTS-STARTPTS[kept_v1];"
        f"{AUDIO_CUT}"
        "[kept_v0][kept_a0][kept_v1][kept_a1]concat=n=2:v=1:a=1[cut][acut]"
    )


def test_audio_graph_cuts_the_audio_before_its_filters() -> None:
    assert audio_graph([], "anull") == "[0:a:0]anull[a]"
    assert audio_graph(SPANS, "anull") == (
        f"{cut_graph(SPANS, ('[0:a:0]', '[acut]'))};[acut]anull[a]"
    )


def test_clip_graph_without_cuts_or_audio_filters_is_the_layout() -> None:
    graph = clip_graph(PLAN, "fill", 10.0, SIZE, 30)

    assert graph == layout_graph(PLAN, "fill", 10.0, SIZE, 30)
    assert clip_graph(PLAN, "fill", 10.0, SIZE, 30, audio="anull") == (
        f"{graph};[0:a:0]anull[a]"
    )


def test_clip_graph_cuts_then_captions_and_filters_the_audio(tmp_path: Path) -> None:
    captions = tmp_path / "1.ass"
    framed = layout_graph(PLAN, "fill", 10.0, SIZE, 30, out="[framed]")

    graph = clip_graph(
        PLAN, "fill", 10.0, SIZE, 30, captions, spans=SPANS, audio="anull"
    )

    assert graph == (
        f"{framed};{cut_graph(SPANS, ('[0:a:0]', '[acut]'), ('[framed]', '[cut]'))};"
        f"[cut]{subtitles_filter(captions)}[v];[acut]anull[a]"
    )


def test_clip_graph_cut_alone_writes_the_parts_to_v_and_a() -> None:
    framed = layout_graph(PLAN, "fill", 10.0, SIZE, 30, out="[framed]")

    assert clip_graph(PLAN, "fill", 10.0, SIZE, 30, spans=SPANS) == (
        f"{framed};{cut_graph(SPANS, ('[0:a:0]', '[a]'), ('[framed]', '[v]'))}"
    )


def test_render_clip_fails_when_the_cuts_leave_nothing(tmp_path: Path) -> None:
    output = tmp_path / "output" / "1.mp4"
    output.parent.mkdir()
    output.write_bytes(b"an older render")

    with pytest.raises(RenderError, match="the cuts of 1.mp4 leave nothing of it"):
        render_clip(
            tmp_path / "source.mp4",
            output,
            10.0,
            12.0,
            PLAN,
            "fill",
            RenderSettings(),
            cut_ranges=[(9.0, 13.0)],
        )

    assert not output.exists()
