"""Kinetic captions as libass draws them (SPEC-v3 3.3): frames of each style's
captions on a black frame, and a caption_style item in a Pro Edit render."""

from dataclasses import replace
from pathlib import Path

import numpy as np
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.proedit.captions.kinetic import kinetic_ass
from clipforge.proedit.edl_params import CaptionStyleParams
from clipforge.proedit.render.run import render_plan
from edl_fakes import item, plan
from frames import Pixels, caption_frame, drawn_extent, numbered_frames
from proedit_render import LOSSLESS, base_of, source_video

SIZE = (540, 960)
WORDS = [CaptionWord("Pizza", 0, 1000), CaptionWord("Time", 1000, 2000)]


def frame(
    tmp: Path, time_s: float, words: list[CaptionWord] = WORDS, **fields: object
) -> Pixels:
    """The frame at time_s of the kinetic captions of words with the params
    fields (style pop unless given)."""
    params = CaptionStyleParams.model_validate({"style": "pop", **fields})
    loud = frozenset(w.start for w in words) if fields.get("shake_on_loud") else set()
    ass = tmp / "captions.ass"
    text = kinetic_ass(
        words, params, SIZE, loud=frozenset(loud), emoji_map={"pizza": "🍕"}
    )
    ass.write_text(text, encoding="utf-8")
    return caption_frame(ass, SIZE, time_s)


def test_pop_grows_the_spoken_word_past_its_size_and_settles(tmp_path: Path) -> None:
    one = WORDS[:1]
    first = drawn_extent(frame(tmp_path, 0.0, one))[0]
    peak = drawn_extent(frame(tmp_path, 0.09, one))[0]
    settled = drawn_extent(frame(tmp_path, 0.5, one))[0]

    assert 0.62 * settled < first < 0.8 * settled
    assert settled < peak < 1.12 * settled
    assert drawn_extent(frame(tmp_path, 0.25, one))[0] == settled


def test_bounce_dips_under_its_size_before_settling(tmp_path: Path) -> None:
    sizes = {
        t: drawn_extent(frame(tmp_path, t, style="bounce"))[0]
        for t in (0.0, 0.08, 0.16, 0.5)
    }

    assert sizes[0.0] < sizes[0.5] < sizes[0.08]
    assert sizes[0.16] < sizes[0.5]


def test_neon_draws_a_halo_of_the_highlight_color_around_the_word(
    tmp_path: Path,
) -> None:
    words = [CaptionWord("Pizza", 0, 1000)]
    neon = frame(tmp_path, 0.5, words, style="neon").astype(int)

    magenta = (neon[..., 0] > 150) & (neon[..., 1] < 120) & (neon[..., 2] > 120)
    white = neon.min(axis=2) > 220
    assert magenta.sum() > 2000
    rows, cols = np.nonzero(white)
    halo = np.nonzero(magenta)
    assert halo[1].min() < cols.min() and halo[1].max() > cols.max()
    assert halo[0].min() < rows.min() and halo[0].max() > rows.max()


def test_single_word_draws_only_the_spoken_word(tmp_path: Path) -> None:
    both = drawn_extent(frame(tmp_path, 0.5))[0]
    one = drawn_extent(frame(tmp_path, 0.5, style="single_word"))[0]
    second = frame(tmp_path, 1.5, style="single_word")

    assert one < both * 1.2
    assert drawn_extent(second)[0] > 0
    assert not np.array_equal(second, frame(tmp_path, 0.5, style="single_word"))


def test_a_loud_word_trembles_while_a_calm_one_does_not(tmp_path: Path) -> None:
    calm = frame(tmp_path, 0.2)
    shaking = frame(tmp_path, 0.2, shake_on_loud=True)

    assert not np.array_equal(calm, shaking)
    assert np.array_equal(calm, frame(tmp_path, 0.5))
    assert np.array_equal(
        frame(tmp_path, 0.5), frame(tmp_path, 0.5, shake_on_loud=True)
    )


def test_the_emoji_pops_in_after_its_word(tmp_path: Path) -> None:
    words = [CaptionWord("Pizza", 0, 1000)]
    start = drawn_extent(frame(tmp_path, 0.01, words, emoji=True))[0]
    peak = drawn_extent(frame(tmp_path, 0.09, words, emoji=True))[0]
    plain = drawn_extent(frame(tmp_path, 0.09, words))[0]

    assert peak > plain > 0
    assert peak > start


def test_render_plan_draws_a_caption_item_on_its_words_only(tmp_path: Path) -> None:
    """A Pro Edit render of a black clip draws the words of its caption_style
    item (1.0-2.5 s of the clip) in that window, the word outside it not,
    and leaves no ASS file behind."""
    source = source_video(tmp_path, "color=c=black:s=1280x720", still=True)
    words = (
        CaptionWord("Pizza", 1200, 1800),
        CaptionWord("Time", 1800, 2400),
        CaptionWord("Later", 3000, 3600),
    )
    base = replace(base_of(source), words=words)
    captions = item(
        1, "caption_style", 1.0, 2.5, params={"style": "pop", "shake_on_loud": True}
    )
    output = render_plan(
        base,
        plan([captions], "pro"),
        tmp_path / "captions.mp4",
        quality="proxy",
        settings=LOSSLESS,
    )

    frames = numbered_frames(output, [15, 45, 100])
    assert drawn_extent(frames[15]) == (0, 0)
    assert drawn_extent(frames[45])[0] > 50
    assert drawn_extent(frames[100]) == (0, 0)
    assert sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".ass") == []
