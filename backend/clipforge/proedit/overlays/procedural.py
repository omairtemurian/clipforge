"""The overlay graphics of Pro Edit (SPEC-v3 1.3, 3.4 Skull Moment): original
drawings made in code, so no image is downloaded or bundled for them.

An overlay item's asset (edl_params.OverlayParams.asset) names one of:
- "skull": a bone-white skull with a dark outline, dark eye sockets, nose
  and teeth (DESIGNS: 100 x 110 units);
- "skeleton": a standing skeleton with that skull (100 x 200 units);
- "arrow": a red arrow with a white rim pointing right (rotation_deg turns
  it; 120 x 60 units);
- "circle": a red ring with a white rim, hollow, to circle a spot
  (100 x 100 units);
- "emoji:<emoji>": the emoji drawn in the bundled Noto Emoji font
  (fonts.EMOJI_FONT, OFL, assets/fonts/LICENSES.md), white with a dark
  outline (the font is monochrome); every character must have a glyph in
  the font (variation selector 16 and zero width joiners aside).

sprite(asset, width) draws one as an RGBA image width pixels wide, its
height by its design's aspect, transparent around it. Shapes are drawn
SUPERSAMPLE times larger (less for a sprite so wide that this would pass
MAX_DRAW_PX) and scaled down (Lanczos), which smooths their edges;
Pillow's shape drawing has no anti-aliasing of its own. Drawings
are deterministic: the same asset and width give the same pixels.
"""

import functools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from clipforge.fonts import EMOJI_FONT, bundled_fonts, font_characters

EMOJI_PREFIX = "emoji:"
SUPERSAMPLE = 4
MAX_DRAW_PX = 4096
BONE = (244, 241, 230, 255)
INK = (18, 18, 18, 255)
RIM = (255, 255, 255, 255)
MARK = (232, 28, 36, 255)
OUTLINE = 4.0
EMOJI_STROKE = 0.05
# Characters that draw no glyph of their own in an emoji sequence.
JOINERS = frozenset({0xFE0F, 0x200D})
Point = tuple[float, float]


@dataclass(frozen=True)
class Pen:
    """Draws on draw in design units: a point (u, v) is pixel
    (x + u * scale, y + v * scale)."""

    draw: ImageDraw.ImageDraw
    scale: float
    x: float = 0.0
    y: float = 0.0

    def at(self, u: float, v: float, factor: float = 1.0) -> "Pen":
        """Return a pen drawing factor times smaller designs from (u, v)."""
        return Pen(self.draw, self.scale * factor, *self.point((u, v)))

    def point(self, point: Point) -> Point:
        """Return point in pixels."""
        return self.x + point[0] * self.scale, self.y + point[1] * self.scale

    def box(self, box: Sequence[float], grow: float = 0.0) -> list[float]:
        """Return box (left, top, right, bottom) in pixels, grown by grow
        units on each side."""
        left, top = self.point((box[0] - grow, box[1] - grow))
        right, bottom = self.point((box[2] + grow, box[3] + grow))
        return [left, top, right, bottom]

    def ellipse(
        self, box: Sequence[float], fill: tuple[int, ...], grow: float = 0.0
    ) -> None:
        """Fill the ellipse inside box."""
        self.draw.ellipse(self.box(box, grow), fill=fill)

    def ring(self, box: Sequence[float], color: tuple[int, ...], width: float) -> None:
        """Draw the outline of the ellipse inside box, width units thick."""
        self.draw.ellipse(self.box(box), outline=color, width=self.px(width))

    def rounded(
        self,
        box: Sequence[float],
        radius: float,
        fill: tuple[int, ...],
        grow: float = 0.0,
    ) -> None:
        """Fill box with corners rounded by radius units."""
        self.draw.rounded_rectangle(
            self.box(box, grow), radius=self.px(radius + grow), fill=fill
        )

    def polygon(
        self, points: Sequence[Point], fill: tuple[int, ...], grow: float = 0.0
    ) -> None:
        """Fill the polygon of points, its edge grown by grow units."""
        self.draw.polygon([self.point(p) for p in points], fill=fill)
        if grow:
            self.line([*points, points[0]], fill, 2 * grow)

    def line(
        self, points: Sequence[Point], fill: tuple[int, ...], width: float
    ) -> None:
        """Draw a line through points, width units thick, round joints."""
        self.draw.line(
            [self.point(p) for p in points],
            fill=fill,
            width=self.px(width),
            joint="curve",
        )
        radius = width / 2
        for u, v in (points[0], points[-1]):
            self.ellipse((u - radius, v - radius, u + radius, v + radius), fill)

    def px(self, units: float) -> int:
        """Return units as a whole number of pixels (at least 1)."""
        return max(round(units * self.scale), 1)


def skull(pen: Pen) -> None:
    """Draw the skull (100 x 110 units)."""
    for color, grow in ((INK, OUTLINE), (BONE, 0.0)):
        pen.ellipse((8, 2, 92, 78), color, grow)
        pen.rounded((24, 50, 76, 104), 12, color, grow)
    pen.ellipse((21, 33, 46, 60), INK)
    pen.ellipse((54, 33, 79, 60), INK)
    pen.polygon(((50, 62), (43, 76), (57, 76)), INK)
    pen.line(((30, 88), (70, 88)), INK, 3)
    for x in (37, 44, 50, 56, 63):
        pen.line(((x, 82), (x, 100)), INK, 2.5)


# Bones of the skeleton (100 x 200 units): polylines and their widths.
BONES: tuple[tuple[tuple[Point, ...], float], ...] = (
    (((50, 46), (50, 122)), 6),
    (((26, 54), (74, 54)), 5),
    (((26, 54), (18, 92), (14, 128)), 6),
    (((74, 54), (82, 92), (86, 128)), 6),
    (((43, 132), (39, 166), (36, 194)), 7),
    (((57, 132), (61, 166), (64, 194)), 7),
    *((((34, y + 4), (50, y), (66, y + 4)), 4) for y in (62, 72, 82, 92)),
)
JOINTS = ((14, 128, 5), (86, 128, 5), (36, 194, 5), (64, 194, 5))
PELVIS = (34, 116, 66, 136)


def skeleton(pen: Pen) -> None:
    """Draw the skeleton (100 x 200 units), its bones outlined together."""
    for color, grow in ((INK, OUTLINE), (BONE, 0.0)):
        for points, width in BONES:
            pen.line(points, color, width + 2 * grow)
        for u, v, radius in JOINTS:
            pen.ellipse((u - radius, v - radius, u + radius, v + radius), color, grow)
        pen.ellipse(PELVIS, color, grow)
    pen.ellipse((44, 122, 56, 132), INK)
    skull(pen.at(30, 0, 0.4))


def arrow(pen: Pen) -> None:
    """Draw the arrow pointing right (120 x 60 units)."""
    head = ((70, 4), (116, 30), (70, 56))
    for color, grow in ((RIM, OUTLINE), (MARK, 0.0)):
        pen.rounded((4, 21, 80, 39), 3, color, grow)
        pen.polygon(head, color, grow)


def circle(pen: Pen) -> None:
    """Draw the hollow ring (100 x 100 units)."""
    pen.ring((3, 3, 97, 97), RIM, 14)
    pen.ring((6, 6, 94, 94), MARK, 8)


# Each drawing and its design size in units (width, height).
DESIGNS: dict[str, tuple[Callable[[Pen], None], tuple[int, int]]] = {
    "skull": (skull, (100, 110)),
    "skeleton": (skeleton, (100, 200)),
    "arrow": (arrow, (120, 60)),
    "circle": (circle, (100, 100)),
}
PROCEDURAL_ASSETS = tuple(DESIGNS)


def supersample(width: int) -> int:
    """Return how many times larger a sprite width pixels wide is drawn."""
    return max(min(SUPERSAMPLE, MAX_DRAW_PX // max(width, 1)), 1)


def emoji_font_path() -> Path:
    """Return the path of the bundled emoji font."""
    return bundled_fonts()[EMOJI_FONT]


def asset_problem(asset: str) -> str | None:
    """Return why asset cannot be drawn (module docstring), or None."""
    if asset in DESIGNS:
        return None
    if asset.startswith(EMOJI_PREFIX):
        text = asset.removeprefix(EMOJI_PREFIX)
        drawn = [ord(c) for c in text if ord(c) not in JOINERS]
        if not drawn:
            return f"the overlay asset {asset!r} names no emoji"
        missing = set(drawn) - font_characters(emoji_font_path())
        if missing:
            listed = ", ".join(f"U+{c:04X}" for c in sorted(missing))
            return f"the emoji font has no glyph for {listed} of {asset!r}"
        return None
    names = ", ".join(PROCEDURAL_ASSETS)
    return f"no overlay asset {asset!r} (one of {names} or {EMOJI_PREFIX}<emoji>)"


def sprite(asset: str, width: int) -> Image.Image:
    """Return asset (asset_problem must be None) drawn width pixels wide
    (module docstring)."""
    if asset.startswith(EMOJI_PREFIX):
        return emoji_sprite(asset.removeprefix(EMOJI_PREFIX), width)
    draw, (units_w, units_h) = DESIGNS[asset]
    scale = width * supersample(width) / units_w
    big = Image.new("RGBA", (width * supersample(width), math.ceil(units_h * scale)))
    draw(Pen(ImageDraw.Draw(big), scale))
    height = max(round(width * units_h / units_w), 1)
    return big.resize((width, height), Image.Resampling.LANCZOS)


def emoji_sprite(text: str, width: int) -> Image.Image:
    """Return text in the emoji font, white with a dark outline, cut to its
    ink and scaled to width pixels wide."""
    size = width * supersample(width)
    font = _emoji_font(size)
    stroke = max(round(size * EMOJI_STROKE), 1)
    left, top, right, bottom = (
        math.floor(edge) for edge in font.getbbox(text, stroke_width=stroke)
    )
    big = Image.new("RGBA", (right - left, bottom - top))
    ImageDraw.Draw(big).text(
        (-left, -top), text, font=font, fill=RIM, stroke_width=stroke, stroke_fill=INK
    )
    height = max(round(big.height * width / big.width), 1)
    return big.resize((width, height), Image.Resampling.LANCZOS)


@functools.lru_cache(maxsize=8)
def _emoji_font(size: int) -> ImageFont.FreeTypeFont:
    """Return the emoji font at size pixels."""
    return ImageFont.truetype(str(emoji_font_path()), size)
