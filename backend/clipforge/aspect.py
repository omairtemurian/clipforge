"""Aspect ratios of rendered clips (SPEC-v2 3.3): the presets 9:16, 1:1, 4:5
and 16:9, and any custom "W:H" between 1:4 and 4:1.

Pure helpers, with no other clipforge imports, so models can validate with
them and the render steps can size frames with them."""

import re
from math import gcd

PRESETS = ("9:16", "1:1", "4:5", "16:9")
# The shorter side of an output frame; the longer side is at most LONG_SIDE_MAX.
SHORT_SIDE = 1080
LONG_SIDE_MAX = 1920
# The widest shape of a custom ratio, long side over short side.
MAX_RATIO = 4
PATTERN = r"^[1-9][0-9]{0,2}:[1-9][0-9]{0,2}$"
_RATIO = re.compile(PATTERN)


def check_aspect(aspect: str) -> str:
    """Return aspect if it is a "W:H" of 1 to 3 digits each whose long side
    is at most MAX_RATIO times its short side; raise ValueError otherwise."""
    if not _RATIO.fullmatch(aspect):
        raise ValueError(f'aspect must look like "9:16", not {aspect!r}')
    width, height = _parts(aspect)
    if max(width, height) > MAX_RATIO * min(width, height):
        raise ValueError(f"aspect {aspect} is more than {MAX_RATIO}:1 wide or tall")
    return aspect


def aspect_size(aspect: str) -> tuple[int, int]:
    """Return the (width, height) of the output frame of aspect: 1080 pixels
    on its shorter side, and the longer side to match (at most 1920, which
    narrows the shorter one), both even because yuv420p needs it. The
    presets are 1080x1920, 1080x1080, 1080x1350 and 1920x1080."""
    width, height = _parts(check_aspect(aspect))
    long_side, short_side = max(width, height), min(width, height)
    long_px = _even(SHORT_SIDE * long_side / short_side)
    short_px = SHORT_SIDE
    if long_px > LONG_SIDE_MAX:
        long_px = LONG_SIDE_MAX
        short_px = _even(LONG_SIDE_MAX * short_side / long_side)
    return (long_px, short_px) if width > height else (short_px, long_px)


def _parts(aspect: str) -> tuple[int, int]:
    """Return the width and height of "W:H", in lowest terms."""
    width, height = (int(part) for part in aspect.split(":"))
    divisor = gcd(width, height)
    return width // divisor, height // divisor


def _even(value: float) -> int:
    """Round value to the nearest even number."""
    return round(value / 2) * 2
