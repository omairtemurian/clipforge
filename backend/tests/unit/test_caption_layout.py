"""The caption templates' sizes and positions, and where each position puts
the Caption style (STEERING 2026-10-31: smaller captions in the lower
third)."""

import pytest
from clipforge.captions_templates import load_templates
from clipforge.models import CaptionPosition
from clipforge.pipeline.captions import build_ass

# Template -> (size, outline, shadow): about 62% of the sizes before
# 2026-10-31 (karaoke_bold 100, comic 100, neon 92, boxed 80, minimal 64,
# clean_subtitle 60), outline and shadow scaled alike (outline at least 1.5).
SIZES = {
    "karaoke_bold": (62, 3.7, 1.9),
    "comic": (62, 5.0, 3.7),
    "neon": (57, 2.5, 0.0),
    "boxed": (50, 8.8, 0.0),
    "minimal": (40, 1.5, 1.2),
    "clean_subtitle": (37, 1.9, 1.2),
}
# Position -> (Alignment, MarginV) of the Caption style on a 1080x1920 frame.
PLACES: dict[CaptionPosition, tuple[str, str]] = {
    "top": ("8", "346"),
    "middle": ("5", "288"),
    "lower_third": ("2", "422"),
    "bottom": ("2", "288"),
}


def test_every_template_is_small_with_three_words_in_the_lower_third() -> None:
    templates = load_templates()

    assert {
        name: (t.size, t.outline, t.shadow)
        for name, t in templates.items()
        if name in SIZES
    } == SIZES
    for name in SIZES:
        assert templates[name].max_words_per_line == 3
    for template in templates.values():
        assert template.position == "lower_third"


@pytest.mark.parametrize("position", list(PLACES))
def test_each_position_has_its_alignment_and_margin(
    position: CaptionPosition,
) -> None:
    template = load_templates()["karaoke_bold"].model_copy(
        update={"position": position}
    )
    ass = build_ass([], template, (1080, 1920), emoji_map={})
    caption = next(
        line for line in ass.splitlines() if line.startswith("Style: Caption")
    )

    fields = caption.split(",")
    assert (fields[18], fields[21]) == PLACES[position]
