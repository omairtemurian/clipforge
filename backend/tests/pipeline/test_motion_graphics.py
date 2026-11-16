"""Tests of motion graphics (SPEC-v2 3.5, pipeline/motion_graphics and
clip_graphics): the LLM's picks (mocked) of names, numbers, dates and key
phrases are snapped to the words they quote, become text-track items in
the brand style (lower-thirds and number callouts), and a real ffmpeg
render draws them, with the headline, in the brand's color only while
they show."""

import json
from pathlib import Path

import numpy as np
import pytest
from builders import make_clip
from clipforge.brand_style import BrandStyle
from clipforge.clip_graphics import MotionGraphicsError, pick_motion_graphics
from clipforge.config import RenderSettings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.fonts import available_fonts
from clipforge.models import FaceBox, MotionGraphicPick, TextProps
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.headline import headline_item
from clipforge.pipeline.motion_graphics import (
    CALLOUT_Y,
    LOWER_THIRD_Y,
    graphic_props,
    is_motion_graphic,
    motion_graphic_items,
    place_graphics,
    quote_span,
    text_room,
    without_motion_graphics,
)
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.timeline import clip_layers, timeline_of, track_problems
from fakes import FakeLLMClient
from frames import Pixels, frame_at
from sqlmodel import Session, create_engine

STYLE = BrandStyle("Anton", "#00E000")
GREEN = np.array([0, 224, 0])
BLUE = np.array([0, 0, 255])
# What the clip says, in milliseconds of the rendered clip.
WORDS = [
    CaptionWord("Meet", 300, 500),
    CaptionWord("Ada", 500, 800),
    CaptionWord("Lovelace.", 800, 1200),
    CaptionWord("She", 1200, 1400),
    CaptionWord("had", 1400, 1600),
    CaptionWord("40", 1600, 1900),
    CaptionWord("ideas", 1900, 2300),
    CaptionWord("—", 2300, 2300),
    CaptionWord("in", 2400, 2500),
    CaptionWord("1843!", 2500, 3000),
]
ADA = MotionGraphicPick(
    kind="name", text="Ada Lovelace", label="Mathematician", quote="ada lovelace"
)
FORTY = MotionGraphicPick(kind="number", text="40", label="ideas", quote="40 ideas")
YEAR = MotionGraphicPick(kind="date", text="1843", quote="in 1843")


def word(text: str, start: int) -> CaptionWord:
    """Return the word text from start for 200 ms."""
    return CaptionWord(text, start, start + 200)


def test_a_quote_is_found_by_its_words_whatever_their_case_and_punctuation() -> None:
    assert quote_span(WORDS, "Ada Lovelace") == (1, 2)
    assert quote_span(WORDS, "ADA, lovelace!") == (1, 2)
    assert quote_span(WORDS, "ideas in 1843") == (6, 9)
    assert quote_span(WORDS, "Ada Byron") is None
    assert quote_span(WORDS, "...") is None


def test_a_quote_said_twice_is_placed_on_its_first_time() -> None:
    words = [word("go", 0), word("now", 200), word("go", 400), word("now", 600)]

    assert quote_span(words, "go now") == (0, 1)
    assert quote_span(words, "now go") == (1, 2)


def test_graphics_start_on_their_first_word_and_show_two_to_three_and_a_half_s() -> (
    None
):
    placed = place_graphics([FORTY, ADA], WORDS, 4.0, 5)

    assert [(g.pick, g.start, g.end) for g in placed] == [
        (ADA, 0.5, 2.5),
        (FORTY, 1.6, 3.6),
    ]
    long_quote = ADA.model_copy(update={"quote": "Meet Ada Lovelace. She had 40 ideas"})
    [graphic] = place_graphics([long_quote], WORDS, 9.0, 5)
    assert (graphic.start, graphic.end) == (0.3, 2.3)
    slow = [word("A", 0), CaptionWord("long", 200, 5000)]
    [graphic] = place_graphics([ADA.model_copy(update={"quote": "a long"})], slow, 9, 5)
    assert (graphic.start, graphic.end) == (0.0, 3.5)


def test_unsaid_clashing_late_and_extra_picks_are_left_out() -> None:
    unsaid = ADA.model_copy(update={"quote": "Ada Byron"})
    clash = MotionGraphicPick(kind="phrase", text="Big ideas", quote="She had")

    assert place_graphics([unsaid, ADA, clash, FORTY], WORDS, 9.0, 5) == place_graphics(
        [ADA, FORTY], WORDS, 9.0, 5
    )
    # The year (callout from 2.4 s) clashes with the 40 (callout to 3.6 s).
    assert [g.pick for g in place_graphics([FORTY, YEAR], WORDS, 9.0, 5)] == [FORTY]
    assert [g.pick for g in place_graphics([YEAR, ADA], WORDS, 9.0, 5)] == [ADA, YEAR]
    assert [g.pick for g in place_graphics([YEAR, ADA], WORDS, 9.0, 1)] == [YEAR]
    # The clip ends 0.5 s after the year is said.
    assert place_graphics([YEAR], WORDS, 2.9, 5) == []


def test_names_and_phrases_are_lower_thirds_numbers_and_dates_callouts() -> None:
    name = graphic_props(ADA, STYLE)
    number = graphic_props(FORTY, STYLE)

    assert (name.text, name.font, name.color, name.box) == (
        "Ada Lovelace\nMathematician",
        "Anton",
        "#FFFFFF",
        "#00E000",
    )
    assert (name.y, name.animation_in, name.animation_out) == (
        LOWER_THIRD_Y,
        "slide_right",
        "fade",
    )
    assert (number.text, number.font, number.color, number.box) == (
        "40\nideas",
        "Anton",
        "#00E000",
        None,
    )
    assert (number.y, number.stroke) == (CALLOUT_Y, "#111111")
    assert number.animation_in == "pop"
    assert graphic_props(YEAR, STYLE).text == "1843"


def test_long_text_wraps_and_shrinks_to_fit_the_frame() -> None:
    phrase = MotionGraphicPick(
        kind="phrase", text="Every single idea counts in the end", quote="x"
    )
    big = MotionGraphicPick(kind="number", text="$2,500,000,000", quote="x")

    wrapped, shrunk = graphic_props(phrase, STYLE), graphic_props(big, STYLE)

    assert wrapped.text == "Every single idea\ncounts in the end"
    assert wrapped.size == 0.034
    assert shrunk.text == "$2,500,000,000"
    assert shrunk.size == pytest.approx(0.075 * 11 / 14, abs=1e-4)


def test_items_are_valid_text_track_items_in_time_order() -> None:
    items = motion_graphic_items([FORTY, ADA], WORDS, 4.0, STYLE, 5)
    tracks = timeline_of([(0.0, 4.0)]).model_copy(update={"text": items})

    assert [(i.id, i.kind, i.start, i.end) for i in items] == [
        ("mg-0", "text", 0.5, 2.5),
        ("mg-1", "text", 1.6, 3.6),
    ]
    assert TextProps.model_validate(items[1].props) == graphic_props(FORTY, STYLE)
    assert track_problems(tracks, 4.0, {}, available_fonts()) == []
    assert all(is_motion_graphic(item) for item in items)


def test_motion_graphics_replace_each_other_and_leave_room_for_other_text() -> None:
    items = motion_graphic_items([ADA, FORTY], WORDS, 4.0, STYLE, 5)
    own = headline_item("Hello", STYLE, 4.0)
    mine = own.model_copy(update={"id": "mg-note"})

    assert without_motion_graphics([own, *items, mine]) == [own, mine]
    assert text_room([own, *items, mine]) == 3
    assert text_room([own.model_copy(update={"id": f"t{n}"}) for n in range(6)]) == 0


def reply(*picks: MotionGraphicPick) -> str:
    """Return an LLM reply with picks."""
    return json.dumps({"items": [pick.model_dump() for pick in picks]})


def test_the_llm_is_asked_again_for_invalid_replies_and_unsaid_quotes() -> None:
    unsaid = ADA.model_copy(update={"quote": "Ada Byron"})
    llm = FakeLLMClient("no json", reply(FORTY, unsaid), reply(FORTY, ADA))
    clip = make_clip("minimal", title="Ada")

    picks = pick_motion_graphics(llm, clip, WORDS, 3)

    assert picks == [FORTY, ADA]
    (system, first), (_, bad_json), (_, unsaid_quote) = llm.calls
    assert "at most 3 graphics" in system and '"quote"' in system
    assert "$2.5M" in system
    assert first.startswith("What is said in the clip:\nMeet Ada Lovelace. She had")
    assert first.endswith("Title: Ada")
    assert "Your previous reply was not valid" in bad_json
    assert "- items.1.quote: 'Ada Byron' is not said word for word" in unsaid_quote


def test_a_valid_reply_is_kept_after_the_last_try_and_none_is_an_error() -> None:
    unsaid = ADA.model_copy(update={"quote": "Ada Byron"})
    clip = make_clip("minimal")

    kept = pick_motion_graphics(
        FakeLLMClient(reply(unsaid), repeat_last=True), clip, WORDS, 3
    )
    nothing = pick_motion_graphics(FakeLLMClient(reply()), clip, WORDS, 3)

    assert kept == [unsaid] and nothing == []
    with pytest.raises(MotionGraphicsError, match="no valid motion graphics"):
        pick_motion_graphics(FakeLLMClient("[]", repeat_last=True), clip, WORDS, 3)


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 4 s blue clip with the headline and the graphics of ADA (0.5-2.5
    s) and FORTY (1.6-3.6 s) in STYLE, rendered at 180x320."""
    folder = tmp_path_factory.mktemp("motion_graphics")
    source = folder / "source.mp4"
    run_ffmpeg(
        ["-f", "lavfi", "-i", "color=c=blue:size=320x240:rate=30:duration=4"]
        + ["-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=48000"]
        + ["-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source]
    )
    text = [
        headline_item("Ada had ideas", STYLE, 4.0),
        *motion_graphic_items([ADA, FORTY], WORDS, 4.0, STYLE, 5),
    ]
    tracks = timeline_of([(0.0, 4.0)]).model_copy(update={"text": text})
    clip = make_clip("minimal", start=0.0, end=4.0, tracks=tracks)
    with Session(create_engine("sqlite://")) as session:
        layers = clip_layers(session, clip, 30)
    assert [layer.item.id for layer in layers] == ["headline", "mg-0", "mg-1"]
    faces: list[list[FaceBox]] = [[] for _ in sample_times(0.0, 4.0)]
    plan = plan_crop(ClipSpan(7, 0.0, 4.0), "9:16", (320, 240), faces, [])
    return render_clip(
        source, folder / "clip.mp4", 0.0, 4.0, plan, "fill", RenderSettings(),
        size=(180, 320), layers=layers,
    )  # fmt: skip


def green_pixels(frame: Pixels, y: float) -> int:
    """Return how many pixels within 12 px of y times the frame's height
    are about the brand green."""
    middle = round(y * frame.shape[0])
    band = frame[middle - 12 : middle + 12].astype(int)
    return int((np.abs(band - GREEN).sum(axis=2) < 120).sum())


def drawn_pixels(frame: Pixels, y: float) -> int:
    """Return how many pixels within 12 px of y times the frame's height
    are not the blue background."""
    middle = round(y * frame.shape[0])
    band = frame[middle - 12 : middle + 12].astype(int)
    return int((np.abs(band - BLUE).sum(axis=2) > 90).sum())


def test_the_render_draws_each_graphic_in_the_brand_color_while_it_shows(
    rendered: Path,
) -> None:
    before, both, late = (frame_at(rendered, t) for t in (0.3, 2.0, 3.2))

    assert drawn_pixels(before, LOWER_THIRD_Y) == 0
    assert drawn_pixels(before, CALLOUT_Y) == 0
    assert green_pixels(both, LOWER_THIRD_Y) > 300
    assert green_pixels(both, CALLOUT_Y) > 40
    assert drawn_pixels(late, LOWER_THIRD_Y) == 0
    assert green_pixels(late, CALLOUT_Y) > 40


def test_the_render_draws_the_headline_on_a_brand_box_over_the_first_3_s(
    rendered: Path,
) -> None:
    shown, gone = frame_at(rendered, 1.0), frame_at(rendered, 3.3)

    assert green_pixels(shown, 0.12) > 300
    assert drawn_pixels(gone, 0.12) == 0
