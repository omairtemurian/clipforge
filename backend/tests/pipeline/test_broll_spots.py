"""Tests of B-roll spots (SPEC-v2 3.6, pipeline/broll): the clip's
sentences, the LLM's picks (a mocked LLM) checked and sent back when they
are not valid, the spots to review, the B-roll items, and, with ffmpeg, a
full-screen cutaway and a picture-in-picture rendered in their windows."""

import json
from pathlib import Path

import numpy as np
import pytest
from builders import make_clip
from clipforge.assets import add_asset
from clipforge.config import RenderSettings
from clipforge.ffmpeg import probe_media, run_ffmpeg
from clipforge.models import BrollPick, BrollProps, FaceBox, Transcript
from clipforge.pipeline.broll import (
    MAX_SPOT_S,
    MIN_SPOT_S,
    SENTENCE_WORDS_MAX,
    BrollError,
    Sentence,
    broll_item,
    clip_sentences,
    find_spots,
    next_item_id,
    plan_spots,
    search_query,
    spot_window,
    stock_orientation,
)
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.polish import rendered_words
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.timeline import clip_layers, timeline_of
from fakes import FIXTURES, FakeLLMClient
from frames import Pixels, frame_at
from sqlalchemy import Engine
from sqlmodel import Session

SIZE = (180, 320)
BLUE, RED, YELLOW = (0, 0, 255), (255, 0, 0), (255, 255, 0)


def word(text: str, start_ms: int, end_ms: int) -> CaptionWord:
    """Return a caption word."""
    return CaptionWord(text, start_ms, end_ms)


def fixture_sentences() -> list[Sentence]:
    """The sentences of fixtures/transcript.json's clip 0.5-34.35 s."""
    transcript = Transcript.model_validate_json(
        (FIXTURES / "transcript.json").read_text(encoding="utf-8")
    )
    clip = make_clip("karaoke_bold", start=0.5, end=34.35)
    return clip_sentences(rendered_words(transcript, clip, 30))


def reply(*spots: tuple[int, list[str]]) -> str:
    """Return an LLM reply with spots (sentence, keywords)."""
    return json.dumps({"spots": [{"sentence": s, "keywords": k} for s, k in spots]})


def test_sentences_end_at_punctuation_pauses_and_the_word_limit() -> None:
    words = [
        word("Hello", 0, 300),
        word("there!", 300, 600),
        word(" ", 600, 650),
        word("No", 700, 900),
        word("stop", 900, 1100),
        word("here", 2000, 2300),
        word('"done."', 2300, 2600),
    ]
    long = [word(f"w{i}", i * 100, i * 100 + 90) for i in range(SENTENCE_WORDS_MAX + 2)]

    sentences = clip_sentences(words)

    assert sentences == [
        Sentence("Hello there!", 0.0, 0.6),
        Sentence("No stop", 0.7, 1.1),
        Sentence('here "done."', 2.0, 2.6),
    ]
    assert [len(s.text.split()) for s in clip_sentences(long)] == [
        SENTENCE_WORDS_MAX,
        2,
    ]
    assert clip_sentences([]) == []


def test_the_fixture_clip_is_split_into_its_sentences() -> None:
    sentences = fixture_sentences()

    assert [s.text for s in sentences][:2] == ["Hi everyone.", "So, I tried yoga."]
    assert sentences[4] == Sentence(
        "Then I bought one of those smart fridges.", 16.4, 19.2
    )
    assert len(sentences) == 8


def test_the_llm_picks_sentences_and_keywords() -> None:
    llm = FakeLLMClient(reply((4, ["smart fridge", "kitchen"]), (1, ["yoga class"])))
    sentences = fixture_sentences()

    picks = find_spots(llm, sentences, 4, clip_id=7)

    assert picks == [
        BrollPick(sentence=1, keywords=["yoga class"]),
        BrollPick(sentence=4, keywords=["smart fridge", "kitchen"]),
    ]
    [(system, user)] = llm.calls
    assert "B-roll" in system and "at most 4 sentences" in system
    assert '"spots"' in system and '"keywords"' in system
    assert "1: 1.03s-2.40s So, I tried yoga." in user
    assert "4: 16.40s-19.20s Then I bought one of those smart fridges." in user


def test_a_reply_that_breaks_the_rules_is_sent_back_with_its_errors() -> None:
    bad = reply((0, ["hello"]), (4, ["fridge"]), (5, ["hawk"]), (9, ["x"]))
    good = reply((4, ["fridge"]), (6, ["phone notification"]))
    llm = FakeLLMClient("not json", bad, good)

    picks = find_spots(llm, fixture_sentences(), 2, clip_id=7)

    assert [p.sentence for p in picks] == [4, 6]
    assert len(llm.calls) == 3
    second, third = llm.calls[1][1], llm.calls[2][1]
    assert "Your previous reply was not valid" in second
    assert "- spots.0: sentence 0 is the hook" in third
    assert "- spots.2: sentence 5 is next to another spot" in third
    assert "- spots.3: sentence 9 does not exist" in third


def test_after_the_last_try_the_usable_picks_are_kept() -> None:
    llm = FakeLLMClient(reply((3, ["a"]), (3, ["b"]), (6, ["c"])), repeat_last=True)

    picks = find_spots(llm, fixture_sentences(), 1, clip_id=7)

    assert [(p.sentence, p.keywords) for p in picks] == [(3, ["a"])]
    assert len(llm.calls) == MAX_RETRIES + 1


def test_no_valid_reply_raises_and_a_silent_clip_asks_nothing() -> None:
    llm = FakeLLMClient("{}", repeat_last=True)

    with pytest.raises(BrollError, match="no valid B-roll spots for clip 7"):
        find_spots(llm, fixture_sentences(), 3, clip_id=7)
    silent = FakeLLMClient()
    assert find_spots(silent, [], 3, clip_id=7) == []
    assert silent.calls == []


def test_a_spot_shows_from_its_sentence_for_a_bounded_time() -> None:
    assert spot_window(Sentence("a", 1.0, 1.5), 30) == (1.0, 1.0 + MIN_SPOT_S)
    assert spot_window(Sentence("a", 2.0, 4.0), 30) == (2.0, 4.0)
    assert spot_window(Sentence("a", 2.0, 20.0), 30) == (2.0, 2.0 + MAX_SPOT_S)
    assert spot_window(Sentence("a", 9.0, 12.0), 10.0) is None
    assert spot_window(Sentence("a", 8.0, 12.0), 10.0) == (8.0, 10.0)


def test_spots_to_review_have_their_sentence_window_and_query() -> None:
    sentences = [
        Sentence("hook", 0.0, 1.0),
        Sentence("one", 1.0, 1.2),
        Sentence("two", 2.0, 3.0),
        Sentence("three", 3.0, 4.0),
        Sentence("four", 9.5, 10.0),
    ]
    picks = [
        BrollPick(sentence=3, keywords=["city", "traffic", "city"]),
        BrollPick(sentence=1, keywords=["coffee cup"]),
        BrollPick(sentence=2, keywords=["overlaps"]),
        BrollPick(sentence=4, keywords=["too late"]),
    ]

    spots = plan_spots(picks, sentences, 10.0)

    assert [(s.sentence, s.start, s.end, s.query) for s in spots] == [
        (1, 1.0, 2.5, "coffee cup"),
        (3, 3.0, 4.5, "city traffic"),
    ]
    assert spots[1].text == "three" and spots[1].keywords == ["city", "traffic", "city"]
    assert spots[0].results == [] and spots[0].error is None
    assert search_query([" a ", "b", "a", ""]) == "a b"


def test_stock_shape_follows_the_clip_or_is_landscape_for_pip() -> None:
    assert stock_orientation("9:16", "cutaway") == "portrait"
    assert stock_orientation("16:9", "cutaway") == "landscape"
    assert stock_orientation("1:1", "cutaway") == "square"
    assert stock_orientation("9:16", "pip") == "landscape"


def test_items_get_free_ids_and_end_with_their_video() -> None:
    tracks = timeline_of([(0.0, 10.0)])
    first = broll_item("broll-1", 3, "video", 1.0, 4.0, BrollProps(), 10.0)
    tracks = tracks.model_copy(update={"broll": [first]})
    pip = BrollProps(mode="pip", offset=1.5, width=0.5)

    short = broll_item("broll-2", 4, "video", 2.0, 6.0, pip, asset_seconds=3.0)
    image = broll_item("broll-3", 5, "image", 2.0, 6.0, BrollProps(), None)

    assert next_item_id(tracks) == "broll-2"
    assert (first.start, first.end) == (1.0, 4.0)
    assert (short.start, short.end) == (2.0, 3.5)
    assert short.props["mode"] == "pip" and short.props["width"] == 0.5
    assert (image.start, image.end) == (2.0, 6.0)
    with pytest.raises(ValueError, match="before its offset"):
        broll_item("x", 4, "video", 0.0, 1.0, BrollProps(offset=3.0), 3.0)


def lavfi(path: Path, *sources: str, args: tuple[str, ...] = ()) -> Path:
    """Encode the lavfi sources into path and return it."""
    inputs = [arg for source in sources for arg in ("-f", "lavfi", "-i", source)]
    run_ffmpeg([*inputs, *args, path])
    return path


def colour(frame: Pixels, x: int, y: int) -> tuple[int, int, int]:
    """Return the mean RGB colour of frame's 4x4 pixels around (x, y)."""
    mean = frame[y - 2 : y + 2, x - 2 : x + 2].reshape(-1, 3).mean(axis=0)
    return int(mean[0]), int(mean[1]), int(mean[2])


def near(actual: tuple[int, int, int], expected: tuple[int, int, int]) -> bool:
    """Return whether actual is expected, give or take compression."""
    return all(abs(a - b) <= 40 for a, b in zip(actual, expected, strict=True))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """A 4 s blue 320x240 source with silence, a red 2 s portrait video
    and a yellow 3 s 160x90 landscape video."""
    folder = tmp_path_factory.mktemp("broll")
    h264 = ("-c:v", "libx264", "-pix_fmt", "yuv420p")
    return {
        "source": lavfi(
            folder / "source.mp4",
            "color=c=blue:size=320x240:rate=30:duration=4",
            "anullsrc=channel_layout=mono:sample_rate=48000:duration=4",
            args=(*h264, "-c:a", "aac", "-shortest"),
        ),
        "red": lavfi(
            folder / "red.mp4", "color=c=red:size=90x160:rate=30:duration=2", args=h264
        ),
        "yellow": lavfi(
            folder / "yellow.mp4",
            "color=c=yellow:size=160x90:rate=30:duration=3",
            args=h264,
        ),
    }


@pytest.fixture
def rendered(engine: Engine, media: dict[str, Path], tmp_path: Path) -> Path:
    """The clip 0-4 s of the source with a cutaway (red, 0.5-1.5 s) and a
    picture-in-picture half the frame wide at a third of its height
    (yellow, 2-3 s), rendered at SIZE."""
    with Session(engine) as session:
        red = add_asset(session, "video", str(media["red"]), "Pexels License").id
        yellow = add_asset(session, "video", str(media["yellow"]), "Pixabay").id
        pip = BrollProps(mode="pip", x=0.5, y=0.3, width=0.5)
        items = [
            broll_item("broll-1", red, "video", 0.5, 1.5, BrollProps(), 2.0),
            broll_item("broll-2", yellow, "video", 2.0, 3.0, pip, 3.0),
        ]
        tracks = timeline_of([(0.0, 4.0)]).model_copy(update={"broll": items})
        clip = make_clip("minimal", start=0.0, end=4.0, tracks=tracks)
        layers = clip_layers(session, clip, 30)
    assert len(layers) == 2
    faces: list[list[FaceBox]] = [[] for _ in sample_times(0.0, 4.0)]
    plan = plan_crop(ClipSpan(7, 0.0, 4.0), "9:16", (320, 240), faces, [])
    return render_clip(
        media["source"],
        tmp_path / "clip.mp4",
        0.0,
        4.0,
        plan,
        "fill",
        RenderSettings(),
        size=SIZE,
        layers=layers,
    )


def test_cutaway_and_pip_broll_render_in_their_windows(rendered: Path) -> None:
    info = probe_media(rendered)
    before, cutaway = frame_at(rendered, 0.25), frame_at(rendered, 1.0)
    pip, after = frame_at(rendered, 2.5), frame_at(rendered, 3.5)

    assert (info.width, info.height) == SIZE
    assert abs(info.duration - 4.0) <= 0.2
    assert near(colour(before, 90, 160), BLUE)
    # The cutaway fills the frame, corners included.
    assert all(
        near(colour(cutaway, x, y), RED) for x, y in [(4, 4), (90, 160), (175, 315)]
    )
    # The picture-in-picture: 90 px wide, 16:9, centred at (90, 96).
    assert near(colour(pip, 90, 96), YELLOW)
    assert near(colour(pip, 90, 200), BLUE) and near(colour(pip, 20, 96), BLUE)
    yellow = np.all(np.abs(pip.astype(int) - YELLOW) <= 60, axis=2)
    rows, cols = np.flatnonzero(yellow.any(axis=1)), np.flatnonzero(yellow.any(axis=0))
    assert cols[-1] - cols[0] + 1 == pytest.approx(90, abs=3)
    assert rows[-1] - rows[0] + 1 == pytest.approx(50, abs=3)
    assert near(colour(after, 90, 96), BLUE)
