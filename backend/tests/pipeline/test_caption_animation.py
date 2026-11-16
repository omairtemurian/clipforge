"""The caption animations (SPEC-v2 3.4) as libass draws them: frames of a
template's captions at moments of a word, measured on a black frame."""

from pathlib import Path

import numpy as np
from clipforge.captions_templates import get_template
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.captions import build_ass
from frames import Pixels, caption_frame, drawn_extent

SIZE = (540, 960)


def frame(name: str, words: list[CaptionWord], time_s: float, tmp: Path) -> Pixels:
    """Return the frame at time_s of template name's captions of words."""
    ass = tmp / f"{name}.ass"
    text = build_ass(words, get_template(name), SIZE, emoji_map={})
    ass.write_text(text, encoding="utf-8")
    return caption_frame(ass, SIZE, time_s)


def width_at(name: str, time_s: float, tmp: Path) -> int:
    """Return the drawn width of the word "Pizza" (spoken 0-1 s) at time_s."""
    pixels = frame(name, [CaptionWord("Pizza", 0, 1000)], time_s, tmp)
    return drawn_extent(pixels)[0]


def test_a_template_without_animation_draws_the_word_at_one_size(
    tmp_path: Path,
) -> None:
    assert get_template("karaoke_bold").animation == "none"
    assert width_at("karaoke_bold", 0.01, tmp_path) == width_at(
        "karaoke_bold", 0.5, tmp_path
    )


def test_pop_grows_the_spoken_word_to_its_size(tmp_path: Path) -> None:
    start = width_at("pop_punch", 0.0, tmp_path)
    middle = width_at("pop_punch", 0.06, tmp_path)
    settled = width_at("pop_punch", 0.5, tmp_path)

    # 75% at the word's start, full size after 120 ms.
    assert 0.7 * settled < start < 0.82 * settled
    assert start < middle < settled
    assert width_at("pop_punch", 0.2, tmp_path) == settled


def test_bounce_overshoots_by_at_most_five_percent_then_settles(
    tmp_path: Path,
) -> None:
    start = width_at("tidal_bounce", 0.0, tmp_path)
    peak = width_at("tidal_bounce", 0.09, tmp_path)
    settled = width_at("tidal_bounce", 0.5, tmp_path)

    assert start < settled < peak <= 1.06 * settled
    assert peak > 1.03 * settled


def test_fade_brings_a_page_in_from_transparent(tmp_path: Path) -> None:
    words = [CaptionWord("Pizza", 0, 1000)]

    early = frame("soft_fade", words, 0.01, tmp_path).max()
    late = frame("soft_fade", words, 0.3, tmp_path).max()

    assert early < 60
    assert late > 200


def test_reveal_shows_words_once_spoken_without_moving_them(tmp_path: Path) -> None:
    words = [
        CaptionWord("Alpha", 0, 400),
        CaptionWord("Bravo", 400, 800),
        CaptionWord("Delta", 800, 1200),
    ]

    first = frame("storyteller", words, 0.1, tmp_path)
    all_three = frame("storyteller", words, 0.9, tmp_path)

    assert drawn_extent(first)[0] < 0.5 * drawn_extent(all_three)[0]
    # The hidden words keep their place: the first word starts where it does
    # once the whole line shows.
    left = [int(np.flatnonzero(p.max(axis=(0, 2)) > 40)[0]) for p in (first, all_three)]
    assert left[0] == left[1]


def test_a_two_line_template_shows_a_page_of_two_lines(tmp_path: Path) -> None:
    texts = ["One", "Two", "Ten", "Six", "Red", "Hat"]
    words = [CaptionWord(text, 300 * i, 300 * (i + 1)) for i, text in enumerate(texts)]
    template = get_template("headline_duo")
    assert (template.max_lines, template.max_words_per_line) == (2, 3)

    pixels = frame("headline_duo", words, 0.2, tmp_path)

    rows = (pixels.max(axis=(1, 2)) > 40).astype(int)
    bands = int(np.count_nonzero(np.diff(rows) == 1)) + int(rows[0])
    assert bands == 2
