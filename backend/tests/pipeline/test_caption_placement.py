"""Where libass draws captions on a 1080x1920 frame (STEERING 2026-10-31:
captions in the lower third, at most two lines): the rows that a caption's
text covers for each template and position."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.captions_templates import CaptionTemplate, load_templates
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import CaptionPosition
from clipforge.pipeline.caption_effects import PILL_SIZE_RATIO
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.captions import build_ass
from clipforge.pipeline.render_graph import subtitles_filter

WIDTH, HEIGHT = 1080, 1920
SHORT = ("Hey", "you", "there")
# Three words too wide for one line of the large templates: libass wraps them.
LONG = ("Unbelievable", "extraordinary", "performance")
# Position -> the band of the frame, as fractions of its height, that a
# caption line (or two wrapped lines) stays in.
BANDS: dict[CaptionPosition, tuple[float, float]] = {
    "top": (0.18, 0.24),
    "middle": (0.47, 0.53),
    "lower_third": (0.7, 0.78),
    "bottom": (0.79, 0.85),
}
TEMPLATES = load_templates()


def reach(template: CaptionTemplate) -> int:
    """Return how many rows past the text a template draws: the pill's border."""
    return round(template.size * PILL_SIZE_RATIO) if template.animation == "pill" else 0


def text_rows(template: CaptionTemplate, words: tuple[str, ...], tmp: Path) -> range:
    """Return the rows of a black 1080x1920 frame that libass draws template's
    caption of words on (the text, not the outline or box, drawn black)."""
    ass = tmp / "caption.ass"
    timed = [CaptionWord(text, 0, 1000) for text in words]
    black = template.model_copy(update={"outline_color": "#000000"})
    ass.write_text(
        build_ass(timed, black, (WIDTH, HEIGHT), emoji_map={}), encoding="utf-8"
    )
    result = run_ffmpeg(
        ["-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:r=10:d=1"]
        + ["-vf", subtitles_filter(ass), "-ss", "0.5", "-frames:v", "1"]
        + ["-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    )
    pixels = np.frombuffer(result.stdout, np.uint8).reshape(HEIGHT, WIDTH, 3)
    drawn = np.flatnonzero(pixels.max(axis=(1, 2)) > 40)
    return range(int(drawn[0]), int(drawn[-1]) + 1)


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("position", list(BANDS))
def test_each_position_draws_in_its_band(
    name: str, position: CaptionPosition, tmp_path: Path
) -> None:
    template = TEMPLATES[name].model_copy(update={"position": position})
    top, bottom = BANDS[position]

    for words in (SHORT, LONG):
        rows = text_rows(template, words, tmp_path)
        assert round(top * HEIGHT) <= rows.start + reach(template), (words, rows)
        assert rows.stop <= round(bottom * HEIGHT) + reach(template), (words, rows)


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_default_captions_sit_in_the_lower_third_in_at_most_two_lines(
    name: str, tmp_path: Path
) -> None:
    template = TEMPLATES[name]
    short = text_rows(template, SHORT, tmp_path)
    long = text_rows(template, LONG, tmp_path)

    assert template.position == "lower_third"
    # Both end at the same row (bottom aligned) above 78% of the height; round
    # letters (the C of PERFORMANCE) overshoot the baseline by up to 1 px when
    # the other line has none (one- and two-word lines).
    assert abs(long.stop - short.stop) <= 1 + reach(template)
    assert max(long.stop, short.stop) <= round(0.78 * HEIGHT) + reach(template)
    # A wrapped caption is at most two lines: less than three lines tall.
    assert len(long) < 3 * template.size
    assert long.start >= round(0.7 * HEIGHT)
