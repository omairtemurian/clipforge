"""Tests of text overlays (SPEC-v2 3.5, pipeline/text_overlay): at most
five text items per clip, their drawtext filters (font, size, colors,
stroke, box, position, in/out animations), and a real ffmpeg render whose
frames show each text only in its window, fading, sliding and popping."""

from pathlib import Path

import numpy as np
import pytest
from builders import make_clip
from builders import track_item as item
from clipforge.config import RenderSettings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.fonts import available_fonts
from clipforge.models import FaceBox, TextProps, TrackItem
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.text_overlay import (
    MAX_TEXT_LAYERS,
    animation_seconds,
    text_filter,
    text_layer_problems,
)
from clipforge.timeline import clip_layers, timeline_of, track_problems
from frames import Pixels, frame_at
from sqlalchemy import Engine
from sqlmodel import Session, create_engine

FONT = Path("/fonts/A.ttf")
SIZE = (180, 320)
# The clip is 0-4 s of the source; the cut 0.2-0.6 s leaves 3.6 s.
CUTS = [(0.2, 0.6)]
LENGTH = 3.6
BLUE = np.array([0, 0, 255])


def texts(count: int) -> list[TrackItem]:
    """Return count text items, one after another."""
    return [item(f"t{n}", "text", n * 0.5, n * 0.5 + 0.4, props={"text": "Hi"})
            for n in range(count)]  # fmt: skip


def test_five_text_layers_are_allowed_and_a_sixth_is_refused() -> None:
    five = timeline_of([(0.0, 4.0)]).model_copy(update={"text": texts(5)})
    six = five.model_copy(update={"text": texts(6)})

    assert MAX_TEXT_LAYERS == 5
    assert text_layer_problems(five.text) == []
    assert track_problems(five, LENGTH, {}, available_fonts()) == []
    assert track_problems(six, LENGTH, {}, available_fonts()) == [
        "text track: 6 text overlays, at most 5 allowed"
    ]


def test_an_unknown_animation_is_a_props_problem() -> None:
    bad = item("t", "text", 0, 1, props={"text": "Hi", "animation_in": "spin"})
    tracks = timeline_of([(0.0, 4.0)]).model_copy(update={"text": [bad]})

    [problem] = track_problems(tracks, LENGTH, {}, available_fonts())

    assert problem.startswith("text item 't': props animation_in:")


def test_render_keeps_only_the_first_five_text_items(engine: Engine) -> None:
    tracks = timeline_of([(0.0, 4.0)]).model_copy(update={"text": texts(6)})
    clip = make_clip("minimal", start=0.0, end=4.0, tracks=tracks)

    with Session(engine) as session:
        layers = clip_layers(session, clip, 30)

    assert [layer.item.id for layer in layers] == ["t0", "t1", "t2", "t3", "t4"]


def test_a_still_text_has_its_font_size_colors_stroke_box_and_position() -> None:
    props = TextProps(
        text="a:b", size=0.1, color="#FFEE00", stroke="#112233", stroke_width=0.1,
        box="#000000", box_opacity=0.5, x=0.25, y=0.75,
    )  # fmt: skip

    drawn = text_filter(props, FONT, 320, 1.0, 2.0)

    assert drawn == (
        r"drawtext=fontfile=/fonts/A.ttf:text=a\\:b:expansion=none:fontsize=32"
        ":fontcolor=0xFFEE00:borderw=3:bordercolor=0x112233"
        ":x=w*0.25-text_w/2:y=h*0.75-text_h/2"
        ":box=1:boxcolor=0x000000@0.5:boxborderw=8"
    )


def test_animations_are_expressions_of_the_frame_time() -> None:
    props = TextProps(
        text="Hi", animation_in="pop", animation_out="slide_up", in_seconds=0.5
    )

    drawn = text_filter(props, FONT, 100, 1.0, 3.0)

    shown_in = "(1-pow(1-clip((t-1.000)/0.500,0,1),2))"
    shown_out = "(1-pow(1-clip((3.000-t)/0.400,0,1),2))"
    assert f"fontsize='6*(0.6+0.4*{shown_in})'" in drawn
    assert f"y='h*0.2-text_h/2-h*0.15*(1-{shown_out})'" in drawn
    assert "x=w*0.5-text_w/2:" in drawn
    assert f"alpha='{shown_in}*{shown_out}'" in drawn


@pytest.mark.parametrize(
    ("animation", "x_shift", "y_shift"),
    [
        ("slide_up", "", "+h*0.15"),
        ("slide_down", "", "-h*0.15"),
        ("slide_left", "+w*0.15", ""),
        ("slide_right", "-w*0.15", ""),
        ("fade", "", ""),
    ],
)
def test_a_slide_in_starts_off_its_place_against_its_direction(
    animation: str, x_shift: str, y_shift: str
) -> None:
    props = TextProps.model_validate({"text": "Hi", "animation_in": animation})

    drawn = text_filter(props, FONT, 100, 0.0, 2.0)

    x = "w*0.5-text_w/2" + (f"{x_shift}*(1-" if x_shift else "")
    y = "h*0.2-text_h/2" + (f"{y_shift}*(1-" if y_shift else "")
    assert (f"x='{x}" if x_shift else f"x={x}:") in drawn
    assert (f"y='{y}" if y_shift else f"y={y}:") in drawn
    assert "alpha='(1-pow(1-clip((t-0.000)/0.400,0,1),2))'" in drawn


def test_animations_longer_than_the_item_are_shortened_in_proportion() -> None:
    both = TextProps(text="Hi", animation_in="fade", animation_out="pop",
                     in_seconds=3, out_seconds=1)  # fmt: skip
    only_out = both.model_copy(update={"animation_in": "none"})

    assert animation_seconds(both, 2.0) == (1.5, 0.5)
    assert animation_seconds(both, 5.0) == (3.0, 1.0)
    assert animation_seconds(only_out, 0.5) == (0.0, 0.5)
    assert animation_seconds(TextProps(text="Hi"), 0.1) == (0.0, 0.0)


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 4 s blue 320x240 source with silence."""
    path = tmp_path_factory.mktemp("text_overlay") / "source.mp4"
    run_ffmpeg(
        ["-f", "lavfi", "-i", "color=c=blue:size=320x240:rate=30:duration=4"]
        + ["-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=48000"]
        + ["-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path]
    )
    return path


def band(
    item_id: str, start: float, end: float, y: float, **props: object
) -> TrackItem:
    """Return a text item "WWW" of size 0.06 centered at y."""
    return item(item_id, "text", start, end,
                props={"text": "WWW", "size": 0.06, "y": y} | props)  # fmt: skip


@pytest.fixture(scope="module")
def rendered(source: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The clip 0-4 s of the source with CUTS and five text overlays, each
    in its own band of the frame, rendered at SIZE (text items play no
    asset, so an empty in-memory library serves them)."""
    tracks = timeline_of([(0.0, 4.0)]).model_copy(
        update={
            "text": [
                band("fade", 1.0, 2.5, 0.1, color="#FF0000", box="#FF0000",
                     animation_in="fade", animation_out="fade", in_seconds=0.5,
                     out_seconds=0.5),
                band("slide", 1.0, 3.0, 0.3, color="#00FF00", box="#00FF00",
                     animation_in="slide_right", in_seconds=1.0),
                band("pop", 1.0, 3.0, 0.5, animation_in="pop", in_seconds=1.0),
                band("stroke", 0.0, 3.6, 0.7, size=0.1, stroke="#000000",
                     stroke_width=0.2),
                band("half", 0.0, 1.0, 0.9, color="#FFFF00", box="#FFFF00",
                     box_opacity=0.5),
            ]
        }
    )  # fmt: skip
    clip = make_clip("minimal", start=0.0, end=4.0, cut_ranges=CUTS, tracks=tracks)
    with Session(create_engine("sqlite://")) as session:
        layers = clip_layers(session, clip, 30)
    assert len(layers) == 5
    faces: list[list[FaceBox]] = [[] for _ in sample_times(0.0, 4.0)]
    plan = plan_crop(ClipSpan(7, 0.0, 4.0), "9:16", (320, 240), faces, [])
    output = tmp_path_factory.mktemp("text_render") / "clip.mp4"
    return render_clip(
        source, output, clip.start, clip.end, plan, "fill", RenderSettings(),
        cut_ranges=CUTS, size=SIZE, layers=layers,
    )  # fmt: skip


def rows(frame: Pixels, y: float) -> Pixels:
    """Return the rows of frame within 22 px of y times its height."""
    middle = round(y * frame.shape[0])
    return frame[middle - 22 : middle + 22].astype(int)


def drawn(pixels: Pixels) -> Pixels:
    """Return the mask of the pixels that are not the blue background."""
    return np.abs(pixels - BLUE).sum(axis=2) > 90


def mean_colour(frame: Pixels, y: float) -> Pixels:
    """Return the mean colour of the drawn pixels of the band at y."""
    band_pixels = rows(frame, y)
    return band_pixels[drawn(band_pixels)].mean(axis=0)


def test_fade_text_shows_only_in_its_window_and_fades(rendered: Path) -> None:
    before, early, full = (frame_at(rendered, t) for t in (0.8, 1.1, 1.75))
    late, after = frame_at(rendered, 2.45), frame_at(rendered, 2.8)

    assert not drawn(rows(before, 0.1)).any()
    assert not drawn(rows(after, 0.1)).any()
    red_full = rows(full, 0.1)[..., 0].max()
    red_early, red_late = rows(early, 0.1)[..., 0].max(), rows(late, 0.1)[..., 0].max()
    assert red_full > 230
    assert 40 < red_early < red_full - 60
    assert 40 < red_late < red_full - 60


def test_slide_in_moves_the_text_into_its_place(rendered: Path) -> None:
    def centre(t: float) -> float:
        return float(
            np.flatnonzero(drawn(rows(frame_at(rendered, t), 0.3)).any(axis=0)).mean()
        )

    assert not drawn(rows(frame_at(rendered, 0.9), 0.3)).any()
    sliding, settled = centre(1.25), centre(2.0)
    assert settled == pytest.approx(90, abs=3)
    assert settled - sliding > 8


def test_pop_in_grows_the_text(rendered: Path) -> None:
    def width(t: float) -> int:
        return int(drawn(rows(frame_at(rendered, t), 0.5)).any(axis=0).sum())

    small, full = width(1.15), width(2.0)
    assert 0 < small < full * 0.85


def test_stroke_and_half_opaque_box_colors(rendered: Path) -> None:
    frame = frame_at(rendered, 0.5)

    stroke_band = rows(frame, 0.7)
    assert (stroke_band.max(axis=2) < 40).sum() > 50
    assert (stroke_band.min(axis=2) > 215).sum() > 50
    # A yellow box at half opacity over blue: about (128, 128, 128).
    yellow_half = mean_colour(frame, 0.9)
    assert yellow_half == pytest.approx([128, 128, 128], abs=40)
    assert not drawn(rows(frame_at(rendered, 1.3), 0.9)).any()
