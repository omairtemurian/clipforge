"""The brand style of a project's text graphics (SPEC-v2 3.5): the font and
primary color of the brand template that its settings pick
(ProcessingSettings.brand_template_id; clip_graphics.project_brand), or
ClipForge's defaults without one. The auto headline (pipeline/headline)
and motion graphics (pipeline/motion_graphics) are drawn in it.
"""

import logging
from collections.abc import Collection
from dataclasses import dataclass

from clipforge.models import BrandTemplate

logger = logging.getLogger(__name__)

# The font and color of a new brand template, and of graphics without one.
DEFAULT_FONT = "Inter Bold"
DEFAULT_COLOR = "#FF6B35"


@dataclass(frozen=True)
class BrandStyle:
    """The font (a bundled or uploaded font's name) and primary color
    (#RRGGBB) that text graphics are drawn in."""

    font: str
    color: str


def brand_style(brand: BrandTemplate | None, fonts: Collection[str]) -> BrandStyle:
    """Return the style of brand: its font, if it is one of fonts (else
    DEFAULT_FONT, logged), and its primary color; the defaults for None."""
    if brand is None:
        return BrandStyle(DEFAULT_FONT, DEFAULT_COLOR)
    font = brand.font
    if font not in fonts:
        logger.warning(
            "brand template %d: font %r is gone; using %s", brand.id, font, DEFAULT_FONT
        )
        font = DEFAULT_FONT
    return BrandStyle(font, brand.primary_color)
