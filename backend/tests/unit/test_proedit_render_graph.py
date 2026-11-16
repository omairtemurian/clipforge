"""Unit tests of the Pro Edit renderer's filters and frame sizes (SPEC-v3
3.6, TASK-207/208/210/211): the enable windows and frame ranges, the
grade-track filters (normalization, protected looks, LUTs) and their order,
freeze and flash filters, the order of the speed, freeze, zoom/shake,
transition, grade, glitch and flash stages, the items the renderer
refuses, the graph's labels and the proxy and final frame sizes. The
frames themselves are tested with ffmpeg in
tests/pipeline/test_proedit_render_core.py."""

from pathlib import Path
from typing import Any

import pytest
from clipforge.config import RenderSettings
from clipforge.models import EdlKind
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.proedit.edl import TypedEdlItem, parse_item
from clipforge.proedit.render.base import ProEditBase
from clipforge.proedit.render.canvas import Canvas
from clipforge.proedit.render.fx_basic import (
    LUT_CACHE_DIRNAME,
    flash_filters,
    freeze_filters,
)
from clipforge.proedit.render.fx_glitch import glitch_filters
from clipforge.proedit.render.fx_transition import transition_filters
from clipforge.proedit.render.grade import grade_filters
from clipforge.proedit.render.graph import (
    PRO_AUDIO,
    PRO_VIDEO,
    proedit_graph,
    undrawn,
    video_chain,
)
from clipforge.proedit.render.luts import bundled_path
from clipforge.proedit.render.motion import motion_filters
from clipforge.proedit.render.motion_time import camera_filters, time_filters
from clipforge.proedit.render.run import output_size, quality_settings
from clipforge.proedit.render.timing import frame_range, frame_window
from edl_fakes import item

WINDOW = "enable='gte(t,0.983333)*lt(t,1.983333)'"
# A grade change without normalization or skin protection: just its look.
PLAIN = {"normalize": False, "skin_protect": False}


def typed(
    kind: EdlKind, params: dict[str, Any], t_start: float = 1.0, id: int = 1
) -> TypedEdlItem:
    return parse_item(item(id, kind, t_start, t_start + 1.0, params=params))


def test_a_window_holds_the_frames_that_start_in_it() -> None:
    # Frame k starts at k / 30 s: frames 30..59 lie in 1.0-2.0 s.
    assert frame_window(1.0, 2.0, 30) == "gte(t,0.983333)*lt(t,1.983333)"


@pytest.mark.parametrize(
    ("kind", "params", "expected"),
    [
        ("grade_change", {"look": "bw", "normalize": False}, "hue=s=0"),
        ("grade_change", {"look": "bw", "amount": 0.5, **PLAIN}, "hue=s=0.5"),
        ("grade_change", {"look": "desat", **PLAIN}, "hue=s=0.4"),
        (
            "grade_change",
            {"look": "dark", **PLAIN},
            "eq=brightness=-0.06:contrast=1.1:gamma=0.65:saturation=0.8",
        ),
        ("vignette", {}, "vignette=angle=0.6283"),
        ("vignette", {"strength": 1.0}, "vignette=angle=1.5708"),
        ("grain", {"seed": 7}, "noise=c0s=10:c0f=t:c0_seed=7"),
        (
            "grain",
            {"strength": 0.001, "seed": -1},
            "noise=c0s=1:c0f=t:c0_seed=2147483647",
        ),
    ],
)
def test_each_grade_item_is_one_timed_filter(
    kind: EdlKind, params: dict[str, Any], expected: str
) -> None:
    assert grade_filters([typed(kind, params)], 30) == [f"{expected}:{WINDOW}"]


def test_grain_is_added_after_the_grade_whatever_their_times() -> None:
    grain = typed("grain", {}, t_start=0.0, id=1)
    vignette = typed("vignette", {}, t_start=1.0, id=2)
    bw = typed("grade_change", {"look": "bw"}, t_start=2.0, id=3)
    names = [f.split("=")[0] for f in grade_filters([grain, vignette, bw], 30)]
    assert names == ["normalize", "hue", "format", "vignette", "noise"]


def test_items_without_a_stage_or_look_are_undrawn() -> None:
    text = typed("text_pop", {"text": "WOW"}, id=4)
    lut = typed("grade_change", {"look": "lut", "lut": "sepia"}, id=5)
    cat = typed("overlay", {"asset": "cat"}, t_start=11.0, id=16)
    drawn = [
        typed("grain", {}),
        typed("vignette", {}, t_start=2.0, id=2),
        typed("grade_change", {"look": "lut", "lut": "teal_orange"}, id=3),
        typed("freeze_frame", {}, id=6),
        typed("flash", {}, t_start=3.0, id=7),
        typed("zoom_punch", {}, t_start=4.0, id=8),
        typed("pan", {"from_x": 0.4, "from_y": 0.5, "to_x": 0.6, "to_y": 0.5}, id=9),
        typed("shake", {}, t_start=5.0, id=10),
        typed("slowmo", {}, t_start=6.0, id=11),
        typed("speed_ramp", {}, t_start=7.0, id=12),
        typed("glitch", {}, t_start=8.0, id=13),
        typed("rgb_split", {}, t_start=9.0, id=14),
        typed("transition", {}, t_start=10.0, id=15),
        typed("overlay", {"asset": "skull"}, t_start=11.0, id=17),
    ]
    assert undrawn(drawn) == []
    assert undrawn([text, lut, cat, *drawn[:-1]]) == [
        "item 4 (text_pop): the Pro Edit renderer does not draw text_pop items",
        "item 5 (grade_change): the lut sepia is not bundled with the Pro Edit "
        "renderer",
        "item 16 (overlay): no overlay asset 'cat' (one of skull, skeleton, "
        "arrow, circle or emoji:<emoji>)",
    ]


def test_zooms_are_drawn_after_freezes_and_before_the_grade() -> None:
    items = [
        typed("flash", {}, t_start=0.0, id=1),
        typed("grade_change", {"look": "bw", "normalize": False}, id=2),
        typed("zoom_punch", {"scale": 1.2}, t_start=1.0, id=3),
        typed("freeze_frame", {}, t_start=0.5, id=4),
    ]
    canvas = Canvas(30, (540, 960))
    chain = video_chain(items, canvas)
    order = [
        ",".join(freeze_filters([items[3]], 30)),
        ",".join(motion_filters([items[2]], canvas)),
        ",".join(grade_filters([items[1]], 30)),
        ",".join(flash_filters([items[0]], 30)),
    ]
    assert chain == ",".join(["format=yuv420p", *order])


def test_speed_changes_come_first_and_shakes_with_the_zooms() -> None:
    items = [
        typed("freeze_frame", {}, t_start=0.5, id=1),
        typed("zoom_punch", {"scale": 1.2}, t_start=1.0, id=2),
        typed("shake", {"seed": 4}, t_start=2.0, id=3),
        typed("slowmo", {}, t_start=3.0, id=4),
    ]
    canvas = Canvas(30, (540, 960))
    chain = video_chain(items, canvas)
    order = [
        ",".join(time_filters([items[3]], 30)),
        ",".join(freeze_filters([items[0]], 30)),
        ",".join(camera_filters(items[1:3], canvas)),
    ]
    assert chain == ",".join(["format=yuv420p", *order])
    assert camera_filters(items[1:3], canvas) != motion_filters([items[1]], canvas)


def test_transitions_follow_the_zooms_and_glitches_the_grade() -> None:
    items = [
        typed("flash", {}, t_start=0.0, id=1),
        typed("glitch", {"seed": 2}, t_start=1.0, id=2),
        typed("grade_change", {"look": "bw", "normalize": False}, id=3),
        typed("transition", {"type": "glitch"}, t_start=2.0, id=4),
        typed("zoom_punch", {"scale": 1.2}, t_start=3.0, id=5),
        typed("rgb_split", {}, t_start=4.0, id=6),
    ]
    canvas = Canvas(30, (540, 960))
    order = [
        ",".join(motion_filters([items[4]], canvas)),
        ",".join(transition_filters([items[3]], 30)),
        ",".join(grade_filters([items[2]], 30)),
        ",".join(glitch_filters([items[1], items[3], items[5]], canvas)),
        ",".join(flash_filters([items[0]], 30)),
    ]
    assert video_chain(items, canvas) == ",".join(["format=yuv420p", *order])


def test_the_graph_finds_faces_only_for_zooms(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def faces(base: ProEditBase, fps: int, items: Any) -> list[None]:
        calls.append(fps)
        return []

    monkeypatch.setattr("clipforge.proedit.render.graph.subject_faces", faces)
    times = sample_times(1.0, 5.0)
    plan = plan_crop(ClipSpan(7, 1.0, 5.0), "9:16", (1280, 720), [[]] * len(times), [])
    base = ProEditBase(Path("source.mp4"), 1.0, 5.0, plan, "fill")
    proedit_graph(base, [typed("flash", {})], (540, 960), 30)
    assert calls == []
    pan = {"from_x": 0.4, "from_y": 0.5, "to_x": 0.6, "to_y": 0.5}
    proedit_graph(base, [typed("pan", pan)], (540, 960), 30)
    assert calls == [30]


def test_the_graph_draws_the_items_on_the_framed_clip() -> None:
    span = ClipSpan(1, 1.0, 5.0)
    no_faces: list[list[Any]] = [[] for _ in sample_times(span.start, span.end)]
    plan = plan_crop(span, "9:16", (1280, 720), no_faces, [])
    base = ProEditBase(Path("source.mp4"), 1.0, 5.0, plan, "fill")
    items = [typed("grade_change", {"look": "bw", "normalize": False})]
    graph = proedit_graph(base, items, (540, 960), 30)
    canvas = Canvas(30, (540, 960))
    assert graph.endswith(
        f"[v]{video_chain(items, canvas)}{PRO_VIDEO};[a]anull{PRO_AUDIO}"
    )
    assert video_chain(items, canvas) == f"format=yuv420p,hue=s=0:{WINDOW}"
    assert "anull[a]" in graph
    assert base.cuts(30) == []
    cut = ProEditBase(Path("s.mp4"), 1.0, 5.0, plan, "fill", cut_ranges=((2.0, 3.0),))
    assert cut.cuts(30) == [(0.0, 1.0), (2.0, 4.0)]
    assert cut.duration(30) == pytest.approx(3.0)


@pytest.mark.parametrize(
    ("aspect", "quality", "source", "expected"),
    [
        ("9:16", "proxy", (3840, 2160), (540, 960)),
        ("16:9", "proxy", (1280, 720), (960, 540)),
        ("9:16", "final", (1280, 720), (1080, 1920)),
        ("9:16", "final", (640, 360), (1080, 1920)),
        ("9:16", "final", (1920, 1080), (1080, 1920)),
        ("1:1", "final", (2560, 1440), (1440, 1440)),
        ("9:16", "final", (3840, 2160), (2160, 3840)),
        ("16:9", "final", (7680, 4320), (3840, 2160)),
    ],
)
def test_frame_sizes(
    aspect: str,
    quality: Any,
    source: tuple[int, int],
    expected: tuple[int, int],
) -> None:
    assert output_size(aspect, quality, source) == expected


def test_the_proxy_is_faster_at_the_same_quality() -> None:
    settings = RenderSettings(encoder="libx264", crf=20, preset="medium")
    proxy = quality_settings(settings, "proxy")
    assert (proxy.preset, proxy.crf, proxy.encoder) == ("veryfast", 20, "libx264")
    assert quality_settings(settings, "final") == settings


def test_a_frame_range_counts_the_frames_of_the_window() -> None:
    assert frame_range(1.0, 2.0, 30) == (30, 60)
    assert frame_range(0.0, 1 / 30, 30) == (0, 1)
    assert frame_range(1.0, 1.01, 30) == (30, 30)


def test_a_freeze_holds_the_first_frame_of_its_window() -> None:
    later = typed("freeze_frame", {}, t_start=2.0, id=1)
    earlier = typed("freeze_frame", {}, t_start=0.5, id=9)
    assert freeze_filters([later, earlier], 30) == [
        "split[pe_freeze0][pe_held0];[pe_freeze0][pe_held0]"
        "freezeframes=first=15:last=44:replace=15",
        "split[pe_freeze1][pe_held1];[pe_freeze1][pe_held1]"
        "freezeframes=first=60:last=89:replace=60",
    ]


def test_a_flash_peaks_on_its_first_frame_and_fades_out() -> None:
    fade = "clip(1-(t-1.000000)/1.000000,0,1)"
    white = typed("flash", {})
    black = typed("flash", {"color": "black", "peak": 0.5}, t_start=3.0, id=2)
    assert flash_filters([black, white], 30) == [
        f"eq=brightness='0.8*{fade}':saturation='1-0.8*{fade}':eval=frame:{WINDOW}",
        f"eq=brightness='-0.5*{fade.replace('1.000000)', '3.000000)')}'"
        f":saturation='1-0.5*{fade.replace('1.000000)', '3.000000)')}'"
        ":eval=frame:enable='gte(t,2.983333)*lt(t,3.983333)'",
    ]


def test_a_grade_change_normalizes_first_and_protects_skin(data_dir: Path) -> None:
    desat = grade_filters([typed("grade_change", {"look": "desat"})], 30)
    assert desat[0] == f"normalize=smoothing=15:independence=1:strength=0.5:{WINDOW}"
    assert desat[1].startswith(f"lut3d=file={data_dir.absolute() / LUT_CACHE_DIRNAME}")
    assert desat[1].endswith(f".cube:interp=tetrahedral:{WINDOW}")
    assert desat[2:] == ["format=yuv420p"]
    dark = grade_filters(
        [typed("grade_change", {"look": "dark", "normalize": False})], 30
    )
    assert dark[0] == f"eq=brightness=-0.06:contrast=1.1:gamma=0.65:{WINDOW}"
    assert dark[1].startswith("lut3d=") and dark[2:] == ["format=yuv420p"]
    again = grade_filters([typed("grade_change", {"look": "desat"})], 30)
    assert again == desat
    assert len(list((data_dir / LUT_CACHE_DIRNAME).glob("*.cube"))) == 2


def test_a_full_lut_look_without_protection_reads_the_bundled_file(
    data_dir: Path,
) -> None:
    look = {"look": "lut", "lut": "teal_orange", **PLAIN}
    assert grade_filters([typed("grade_change", look)], 30) == [
        f"lut3d=file={bundled_path('teal_orange')}:interp=tetrahedral:{WINDOW}",
        "format=yuv420p",
    ]
    half = grade_filters([typed("grade_change", {**look, "amount": 0.5})], 30)
    assert str(data_dir.absolute() / LUT_CACHE_DIRNAME) in half[0]
